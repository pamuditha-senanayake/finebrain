# contracts_reason.py: Pydantic models for the reasoning seams (K4, K5, K6).
# Used by: scripts/check_golden.py. Uses: contracts_signal.py.
# Source of truth: Docs/CB_System_Reference.md section 6.
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.pipeline.contracts_signal import Money, Principal, Sensitivity, Touches, VersionRef

# Config: enum values copied from the design doc
NodeType = Literal["fact", "policy", "chunk", "skill_step"]
ActionType = Literal[
    "reply_customer", "issue_refund", "apply_credit", "update_cms",
    "schedule_meeting", "fill_template", "request_evidence", "escalate",
]
MAX_RATIONALE_CHARS = 600


# --- K4 ContextQuery and ContextBundle (S6 to S5 and back)

class ContextQuery(BaseModel):
    run_id: str
    principal: Principal
    on_behalf_of: str | None  # effective rights are the intersection with this human
    query_text: str
    entity_refs: list[str] = []
    as_of_valid: datetime | None = None  # None means now
    as_of_recorded: datetime | None = None
    branch: str
    node_types: list[NodeType] | None = None
    top_k: int = 12
    max_tokens: int = 6000


class ItemSource(BaseModel):
    document_id: str
    uri: str
    page: int | None = None
    span: str | None = None  # character offsets as "start:end"


class ContextItem(BaseModel):
    item_id: str
    kind: NodeType
    text: str
    source: ItemSource
    valid_from: datetime | None
    valid_to: datetime | None
    recorded_at: datetime
    verified_by: str | None
    version_ref: VersionRef | None
    score: float
    sensitivity: Sensitivity


class DeniedReason(BaseModel):
    rule_id: str
    count: int


class ContextBundle(BaseModel):
    items: list[ContextItem]  # only allowed items, denied ones are just counted
    denied_count: int
    denied_reasons: list[DeniedReason]
    access_decision_ids: list[str]
    latency_ms: int


# --- K5 ProposedAction (S6 to S7)

class ModelUsage(BaseModel):
    provider: str
    model_id: str
    input_tokens: int
    output_tokens: int


class ProposedAction(BaseModel):
    run_id: str
    step_id: str
    action_type: ActionType
    tool_id: str
    tool_version: int
    arguments: dict  # typed per tool, a refund is { payment_ref, amount, reason_code }
    money: Money | None
    touches: Touches
    rationale_summary: str = Field(max_length=MAX_RATIONALE_CHARS)
    citations: list[str]
    model: ModelUsage
    confidence: float = Field(ge=0, le=1)


# --- K6 AccessCheck and AccessDecision (S5 and S7 to OPA, 10 ms, fail closed)

class Resource(BaseModel):
    type: str
    id: str
    cluster_id: str
    sensitivity: Sensitivity


class AccessCheck(BaseModel):
    check_id: str
    principal: Principal
    on_behalf_of: str | None  # same intersection rule as K4
    action: str  # capability name, for example refund.propose
    resource: Resource


class AccessDecision(BaseModel):
    decision_id: str
    decision: Literal["allow", "deny"]
    rule_id: str
    reason: str
    obligations: list[str] = []
    latency_ms: int
    # Who asked to do what, so the access log reads on its own. Added in step 9; optional so old messages validate.
    principal_id: str | None = None
    on_behalf_of: str | None = None
    action: str | None = None
    resource: str | None = None
    run_id: str | None = None
