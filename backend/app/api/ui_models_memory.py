# ui_models_memory.py: Pydantic copies of the Living memory page's zod contracts (frontend/contracts/memory.ts). They
# serialize in camelCase, so a shape that drifts from the page fails our tests (and the frontend's fixture test), not the browser.
# Used by: memory_views.py, scripts/memory_contract_fixture.py. Uses: ui_models.py, ui_models_work.py (TraceStep).
from typing import Literal

from pydantic import Field

from app.api.ui_models import UiModel
from app.api.ui_models_work import TraceStep

AreaKey = Literal["customer_care", "finance", "legal", "people", "operations", "sales", "product", "general"]
DriftKind = Literal["skill", "policy", "security"]
PolicyCheck = Literal["within", "outside", "unknown"]


# --- The map and its areas

class DriftCounts(UiModel):
    skill: int
    policy: int
    security: int


class AreaSkills(UiModel):
    authored: int
    from_traces: int


class MemoryArea(UiModel):
    key: AreaKey
    name: str
    enabled: bool
    traces7d: int = Field(alias="traces7d")  # the camel-case rule would make it traces7D
    traces_total: int
    patterns: int
    pattern_budget: int
    skills: AreaSkills
    drift: DriftCounts
    surprises: int
    outside_policy: int


class MapTotals(UiModel):
    traces7d: int = Field(alias="traces7d")
    patterns: int
    drift: DriftCounts
    surprises: int


class MemoryMap(UiModel):
    tenant_id: str
    as_of: str
    is_sample: bool
    areas: list[MemoryArea]
    totals: MapTotals


# --- Patterns and drift

class Pattern(UiModel):
    id: str
    area: AreaKey
    name: str
    steps: list[str]
    outcome: str
    policy_check: PolicyCheck
    skill_id: str | None
    week_counts: list[int]
    share: float
    example_trace_ids: list[str]


class DriftSubject(UiModel):
    type: Literal["skill", "policy", "agent"]
    id: str
    name: str


class DriftMetric(UiModel):
    label: str
    usual: float
    latest: float


class DriftFix(UiModel):
    summary: str
    change_request_id: str | None


class DriftRecheck(UiModel):
    until: str
    result: Literal["watching", "dropped", "still_drifting"]


class DriftItem(UiModel):
    id: str
    kind: DriftKind
    area: AreaKey
    subject: DriftSubject
    summary: str
    metric: DriftMetric
    evidence_trace_ids: list[str]
    state: Literal["detected", "sent_to_l1", "awaiting_approval", "approved", "resolved"]
    fix: DriftFix | None
    recheck: DriftRecheck | None
    reopened_note: str | None
    raised_at: str


class AreaDetail(UiModel):
    area: MemoryArea
    patterns: list[Pattern]
    drifts: list[DriftItem]


# --- Traces

class TraceSummary(UiModel):
    id: str
    area: AreaKey
    source: Literal["finebrain", "outside"]
    subject: str
    started_at: str
    ended_at: str | None
    outcome: str
    pattern_id: str | None
    match: Literal["normal", "surprise"]
    policy_check: PolicyCheck
    drift: list[DriftKind]
    run_id: str | None


class TracePage(UiModel):
    items: list[TraceSummary]
    next_cursor: str | None
    total: int


class TraceAccess(UiModel):
    action: str
    principal: str
    on_behalf_of: str | None
    decision: Literal["allow", "deny"]
    rule_id: str
    reason: str
    latency_ms: float


class TracePolicy(UiModel):
    id: str
    name: str
    version: int
    valid_from: str
    valid_to: str | None


class SkillRef(UiModel):
    id: str
    version: int
    branch: str


class TraceDetail(TraceSummary):
    input_ref: str
    steps: list[TraceStep]
    policies: list[TracePolicy]
    skill: SkillRef | None
    access: list[TraceAccess]
    why: list[str]


# --- Skills from traces

class DraftStep(UiModel):
    activity: str
    title: str


class ExtractedSkill(UiModel):
    id: str
    area: AreaKey
    name: str
    pattern_id: str
    steps: list[DraftStep]
    support: int
    same_outcome_share: float
    follow_rate: float
    state: Literal["draft", "in_review", "approved", "rejected"]
    change_request_id: str | None
    created_at: str
