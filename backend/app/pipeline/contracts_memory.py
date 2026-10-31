# contracts_memory.py: Pydantic models for the living memory seams (K16, K17, K18, K19).
# Used by: stages_memory.py, tests/test_memory_skeleton.py. Uses: contracts_signal.py.
# Source of truth: Docs/CB_Living_Memory_Architecture.md sections 3 to 8b, and Docs/CB_System_Reference.md section 6.
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.pipeline.contracts_signal import VersionRef

# Config: enum values from the architecture doc
# The fixed domain list S2 already tags every item with (item_tags.py), so areas and domains are one list
Area = Literal["customer_care", "finance", "legal", "people", "operations", "sales", "product", "general"]
PolicyCheck = Literal["within", "outside", "unknown"]
DriftKind = Literal["skill", "policy", "security"]
# Section 8b: a rejected fix, or one the re-check finds did not hold, goes back to detected
DriftState = Literal["detected", "sent_to_l1", "awaiting_approval", "approved", "resolved"]


# --- K16 TraceRecord (S10 to the trace store)

class TracePolicy(BaseModel):
    policy_ref: VersionRef
    valid_from: datetime
    valid_to: datetime | None


class TraceAccess(BaseModel):
    decision_id: str
    action: str
    principal_id: str
    on_behalf_of: str | None
    decision: Literal["allow", "deny"]
    effective_tier: str | None
    rule_id: str = ""  # added in stage 7 for the trace page; optional so traces kept before validate
    reason: str = ""
    latency_ms: int = 0


class TraceRecord(BaseModel):
    trace_id: str
    tenant_id: str
    area: Area
    source: Literal["finebrain", "outside"]  # outside: a connector event, such as a refund made by hand in Stripe
    started_at: datetime
    ended_at: datetime | None
    input_ref: str
    steps: list[str]  # activity ids in order, from the skill's alphabet (activities.py)
    policies: list[TracePolicy]
    skill: VersionRef | None
    access: list[TraceAccess]
    outcome: str
    decided_by: str | None
    why: list[str]  # one short line per judgment step
    policy_check: PolicyCheck
    run_id: str | None


# --- K17 AreaMatch (triage to the pattern store and To review)

class AreaMatch(BaseModel):
    trace_id: str
    tenant_id: str
    area: Area
    pattern_id: str | None  # None when the trace is a surprise
    pattern_key: str
    similarity: float  # 1.0 for an exact key match
    match: Literal["normal", "surprise"]


# --- K18 DriftFlag (S13 to S8 To review)

class DriftSubject(BaseModel):
    type: Literal["skill", "policy", "agent"]
    id: str
    name: str


class DriftFix(BaseModel):
    summary: str
    change_request_id: str | None


class DriftRecheck(BaseModel):
    until: datetime
    result: Literal["watching", "dropped", "still_drifting"]


class DriftFlag(BaseModel):
    flag_id: str
    tenant_id: str
    kind: DriftKind
    area: Area
    subject: DriftSubject
    summary: str
    usual: float
    latest: float
    evidence_trace_ids: list[str]
    state: DriftState
    fix: DriftFix | None  # None for security drift: it goes to an L1 user as an incident
    recheck: DriftRecheck | None
    reopened_note: str | None
    raised_at: datetime


# --- K19 SkillDraft (S13 to S14 via Studio; becomes a K13 change request)

class SkillDraft(BaseModel):
    draft_id: str
    tenant_id: str
    area: Area
    pattern_id: str
    steps: list[str]
    support: int
    same_outcome_share: float
    follow_rate: float
    state: Literal["draft", "in_review", "approved", "rejected"]
    change_request_id: str | None
    created_at: datetime | None = None  # added in stage 7 for the From traces tab; optional so drafts kept before validate
