# ui_models_work.py: Pydantic copies of the console's work.ts shapes: runs, their steps, escalations, access decisions.
# Used by: views.py (re-exported through ui_models). Uses: ui_models.py (UiModel, VersionRef, Env).
from typing import Literal

from app.api.ui_models import Env, UiModel, VersionRef

RunStatus = Literal["running", "succeeded", "escalated", "failed", "blocked", "awaiting_approval"]
StepKind = Literal["judgment", "tool", "retrieval", "access_check", "quality_gate", "human"]


class Escalation(UiModel):
    reason: str
    risk: Literal["low", "medium", "high"]
    since: str
    assignee: str | None
    criticality: int


class Run(UiModel):
    id: str
    tenant_id: str
    cluster_id: str
    agent_id: str
    skill: VersionRef
    env: Env
    subject: str
    status: RunStatus
    started_at: str
    ended_at: str | None
    escalation: Escalation | None
    conversation_id: str | None
    cost_tokens: int
    cost_usd: float
    latency_ms: int
    human_touch: bool
    failure_class: str | None
    marked_wrong: dict | None = None


class TraceStep(UiModel):
    id: str
    idx: int
    kind: StepKind
    title: str
    decision: str
    reason: str
    duration_ms: int
    at: str
    facts: list[dict]
    access: dict | None
    gate: dict | None
    tool: str | None
    template_fields: list[dict]
    cost_tokens: int


class RunDetail(Run):
    steps: list[TraceStep]


class AccessDecision(UiModel):
    id: str
    tenant_id: str
    at: str
    principal: str
    on_behalf_of: str | None
    action: str
    resource: str
    decision: Literal["allow", "deny"]
    rule_id: str
    reason: str
    latency_ms: float
    run_id: str | None
