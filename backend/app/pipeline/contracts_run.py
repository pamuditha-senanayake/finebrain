# contracts_run.py: Pydantic models for the run seams (K7, K8, K9, K10, K11).
# Used by: scripts/check_golden.py. Uses: contracts_signal.py.
# Source of truth: Docs/CB_System_Reference.md section 6.
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.pipeline.contracts_signal import Criticality, Env, VersionRef

# Config: enum values
Route = Literal["execute", "approval_required", "escalate", "block"]
# awaiting_approval is added on top of the doc's list, matching section 11.3
RunOutcome = Literal["resolved", "escalated", "failed", "blocked", "abandoned", "awaiting_approval", "awaiting_customer"]  # awaiting_customer: the agent asked and waits for the answer


# --- K7 GovernanceVerdict (S7 to S8)

class PolicyResult(BaseModel):
    policy_ref: VersionRef
    passed: bool
    rule_id: str
    explanation: str


class GateResult(BaseModel):
    gate_id: str
    passed: bool
    detail: str


class Approvers(BaseModel):
    tier: str
    count: int
    roles: list[str]


class GovernanceVerdict(BaseModel):
    run_id: str
    step_id: str
    access_decision_id: str
    policy_results: list[PolicyResult]
    quality_gates: list[GateResult]
    criticality: Criticality
    criticality_reasons: list[str]
    route: Route  # a deny always means block
    required_approvers: Approvers | None  # None when the route is execute
    cooling_period_hours: int = 0  # C4 only


# --- K8 ApprovalRequest and Decision (S8)

class ApprovalSubject(BaseModel):
    kind: Literal["action", "change_request", "grant", "evidence"]
    ref: str


class ApprovalRequest(BaseModel):
    approval_id: str
    subject: ApprovalSubject
    criticality: Criticality
    summary_plain: str
    diff_ref: str | None = None
    impact_preview_ref: str | None = None
    evidence_refs: list[str]
    required_approvers: Approvers
    dri_id: str  # exactly one accountable human
    due_at: datetime
    expires_at: datetime  # expiry produces "expired", never a silent skip


class Decision(BaseModel):
    approval_id: str
    decision: Literal["approve", "reject", "request_changes", "delegate", "takeover", "expired"]
    decided_by: list[str]
    decided_at: datetime
    comment: str = ""
    delegated_to: str | None = None
    final_arguments: dict | None = None  # set when a human edited the action


# --- K9 ActionResult (S9 to S10)

class ActionError(BaseModel):
    code: str
    retryable: bool


class ActionResult(BaseModel):
    action_id: str
    run_id: str
    tool_id: str
    idempotency_key: str  # {tenant}:{run_id}:{step_id}, also sent to the outside API
    status: Literal["succeeded", "failed", "retrying", "compensated"]
    external_ref: str | None
    request_hash: str
    response_summary: str  # no personal data
    attempted_at: datetime
    completed_at: datetime | None
    error: ActionError | None


# --- K10 RunRecord (S10 to S13)

class RunStep(BaseModel):
    step_id: str
    kind: Literal["judgment", "tool", "retrieval", "access_check", "quality_gate", "human"]
    started_at: datetime
    duration_ms: int
    decision: str
    reason: str
    refs: list[str]


class TemplateFill(BaseModel):
    template_ref: VersionRef
    field: str
    value_ref: str
    source_item_ids: list[str]
    filled_at: datetime
    fresh_until: datetime


class Cost(BaseModel):
    input_tokens: int
    output_tokens: int
    usd_micro: int


class RunRecord(BaseModel):
    run_id: str
    task_id: str
    agent_id: str
    skill_ref: VersionRef
    outcome: RunOutcome
    steps: list[RunStep]
    template_fills: list[TemplateFill]
    human_touch: bool
    cost: Cost
    latency_ms: int
    trace_object_uri: str
    decided_by: str | None = None  # "auto by policy", or the approvers; None when nothing was let through. Optional so old records validate


# --- K11 UiEvent (S10 to the console)

class UiEvent(BaseModel):
    type: Literal[
        "run.updated", "agent.status", "approval.created", "approval.decided",
        "template.updated", "cr.updated", "gap.created",
    ]
    id: str
    tenant_id: str
    cluster_id: str
    env: Env
    display: dict  # display fields only, personal data stays masked
    at: datetime
