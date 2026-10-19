# contracts_graph.py: Pydantic models for the graph and readiness seams (K13, K14, K15).
# Used by: scripts/check_golden.py. Uses: contracts_signal.py.
# Source of truth: Docs/CB_System_Reference.md section 6. Fields beyond the doc's key fields are a first draft.
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.pipeline.contracts_signal import Criticality, Subject, VersionRef

# Config: enum values
NodeType = Literal[
    "skill", "agent", "policy", "template", "sensor", "scheduler", "loop", "tool",
    "workflow", "access_rule", "fact", "knowledge", "resolver_rule",
]
# close, not delete: nothing is overwritten, a node's valid time ends instead
ChangeOp = Literal["add", "update", "close"]
CommitAuthorKind = Literal["librarian", "learn", "skillify", "studio", "human"]
Verdict = Literal["minimal", "moderate", "breaking"]
ChangeRequestStatus = Literal["draft", "open", "approved", "merged", "rejected", "blocked"]
GapAction = Literal["request_evidence", "create_task", "escalate"]


# --- K13 Commit (S12, S13, Skillify, Workflow Studio to S14)

class CommitAuthor(BaseModel):
    kind: CommitAuthorKind
    id: str


class NodeChange(BaseModel):
    op: ChangeOp
    node_type: NodeType
    node_id: str
    version: int = Field(ge=1)  # the version this change creates
    fields: dict  # full new field set for add and update, empty for close


class Commit(BaseModel):
    commit_id: str
    parent_commit_id: str | None  # None only for the first commit on a branch
    branch: str
    author: CommitAuthor
    message: str
    changes: list[NodeChange] = Field(min_length=1)
    criticality: Criticality
    created_at: datetime


# --- K13 ChangeRequest (the review wrapper around a commit)

class ChangeTest(BaseModel):  # not TestResult, so pytest never tries to collect it
    test_id: str
    passed: bool
    detail: str


class ImpactPreview(BaseModel):
    verdict: Verdict
    affected: list[str]  # node ids inside this workflow
    other_workflows: list[str]  # workflow ids hit through shared tools


class ChangeRequest(BaseModel):
    cr_id: str
    commit_id: str
    plain_diff: str  # what changed in plain words, shown to the approver
    tests: list[ChangeTest]
    impact_preview: ImpactPreview
    status: ChangeRequestStatus
    approval_id: str | None  # set once S8 opens an approval


# --- K14 ReleaseEvent (S14 to S3, S5, S6, S11, compacted topic graph.released)

class ReleaseEvent(BaseModel):
    release_id: str
    commit_id: str
    branch: str
    changed_nodes: list[VersionRef] = Field(min_length=1)
    released_at: datetime


# --- K15 GapDetected (S15 to S3 and S8, topic evidence.gaps)

class GapDetected(BaseModel):
    gap_id: str
    obligation_id: str
    target: Subject  # what the evidence is for, for example a tax filing
    required_item: str
    due_at: datetime
    action: GapAction
    dri_id: str
    escalation_days: int = Field(ge=0)  # days before due_at when the DRI is told
    detected_at: datetime
