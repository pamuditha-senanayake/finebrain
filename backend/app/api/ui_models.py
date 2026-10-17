# ui_models.py: Pydantic copies of the console's zod contracts (frontend/contracts/*.ts) that the API serves:
# shared, org and review shapes. Run shapes (work.ts) live in ui_models_work.py.
# They serialize in camelCase, so a shape that drifts from the console fails our tests, not the browser.
# Used by: views.py, lists.py, ui_models_work.py. Uses: nothing local.
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Tier = Literal["L1", "L2", "L3"]
Env = Literal["production", "staging", "sandbox"]
VoteDecision = Literal["approve", "reject", "request_changes", "delegate"]
ApprovalStatus = Literal["pending", "approved", "rejected", "changes_requested", "expired"]


class UiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    def ui(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


# --- common.ts

class Actor(UiModel):
    kind: Literal["human", "agent", "system"]
    id: str
    name: str


class VersionRef(UiModel):
    id: str
    version: int
    branch: str


# --- org.ts

class Thresholds(UiModel):
    refund_auto_limit_minor: int
    write_off_limit_minor: int
    goodwill_credit_limit_minor: int
    l2_approval_ceiling: int
    cooling_period_hours_c4: int
    approval_expiry_hours: int


class Tenant(UiModel):
    id: str
    name: str
    currency: str
    timezone: str
    locale: str
    brand: dict
    clusters: list[str]
    criticality_thresholds: Thresholds
    is_scale_demo: bool


class Cluster(UiModel):
    id: str
    tenant_id: str
    name: str
    description: str
    status: Literal["active", "planned"]
    connectors: list[str]
    dri: str | None
    health: float
    autonomy_rate: float
    escalation_rate: float
    money_at_stake_minor: int
    open_risks: int
    cost_per_task_usd: float


class Human(UiModel):
    id: str
    tenant_id: str
    name: str
    title: str
    tier: Tier
    roles: list[str]
    attributes: dict[str, str]
    dri_of: list[str]
    max_approval_criticality: int
    color: str


# --- change.ts and ops.ts

class Vote(UiModel):
    by: str
    at: str
    decision: VoteDecision
    comment: str


class Approval(UiModel):
    id: str
    tenant_id: str
    subject: dict
    title: str
    summary: str
    criticality: int
    required_approvers: dict
    votes: list[Vote]
    due_at: str
    created_at: str
    status: ApprovalStatus
    delegated_to: str | None
    dri: str
    drafter: Actor
    evidence: list[str]
    correlation_id: str


class AuditEvent(UiModel):
    id: str
    tenant_id: str
    at: str
    actor: Actor
    action: str
    target: dict
    env: Env
    criticality: int
    detail: str
    correlation_id: str | None
