# stages_version.py: S14 Version, git for the graph. A commit (K13) numbers its node changes; applying it writes the new
# versions on main and releases them (K14 on graph.released). A change request holds a draft commit on its own branch
# until it is approved, then merges, unless a node moved on since it was drafted (a conflict, never a silent overwrite).
# Used by: app/api/studio_apply.py, orchestrate.py (release consumer), tests/test_version.py. Uses: contracts_graph.py, item_tags.py.
from datetime import datetime

from pydantic import BaseModel

from app.pipeline import item_tags
from app.pipeline.contracts_graph import Commit, CommitAuthor, NodeChange, ReleaseEvent
from app.pipeline.contracts_signal import Criticality, VersionRef
from app.pipeline.observe import count, log_event
from app.pipeline.store_graph import CLOSED

# Config
MAIN = "main"


class BranchRecord(BaseModel):
    name: str
    base: str | None
    head: str | None
    status: str  # protected, open, merged, abandoned
    description: str
    created_by: str
    created_at: datetime


class Draft(BaseModel):
    """One change before it is numbered: what to write, and the version it was drafted against."""
    op: str  # add, update, close
    node_type: str
    node_id: str
    fields: dict
    base_version: int  # 0 for a new node


class MergeConflict(Exception):
    """A node in the change moved on after the change was drafted. Someone must redraft it."""


# --- Numbering and writing

def latest_version(graph, node_type: str, node_id: str) -> int:
    history = graph.history(node_type, node_id)
    return history[-1]["_ref"]["version"] if history else 0


def number(lane, drafts: list[Draft]) -> list[NodeChange]:
    """The version each change creates on main, given main as it is now."""
    return [NodeChange(op=d.op, node_type=d.node_type, node_id=d.node_id, version=latest_version(lane.graph, d.node_type, d.node_id) + 1, fields=d.fields)
            for d in drafts]


def head_of(lane, branch: str) -> str | None:
    record = lane.records.load("branch", branch)
    return record["head"] if record else None


def make_commit(lane, author: CommitAuthor, message: str, drafts: list[Draft], criticality: Criticality, branch: str = MAIN) -> Commit:
    return Commit(commit_id=lane.new_id("cmt"), parent_commit_id=head_of(lane, branch), branch=branch, author=author, message=message,
                  changes=number(lane, drafts), criticality=criticality, created_at=lane.now)


def move_head(lane, branch: str, head: str, status: str, by: str, description: str = "", base: str | None = MAIN) -> None:
    stored = lane.records.load("branch", branch)
    record = BranchRecord.model_validate(stored) if stored else BranchRecord(name=branch, base=base, head=None, status=status, description=description, created_by=by, created_at=lane.now)
    lane.records.save("branch", branch, record.model_copy(update={"head": head, "status": status}))


def ensure_main(lane) -> None:
    if lane.records.load("branch", MAIN) is None:
        lane.records.save("branch", MAIN, BranchRecord(name=MAIN, base=None, head=None, status="protected", description="What agents run on", created_by="system", created_at=lane.now))


# --- Applying and releasing

def apply(lane, author: CommitAuthor, message: str, drafts: list[Draft], criticality: Criticality) -> Commit:
    """Commit to main, write every node version, and release. The one way anything changes on main."""
    ensure_main(lane)
    stale = [d.node_id for d in drafts if latest_version(lane.graph, d.node_type, d.node_id) != d.base_version]
    if stale:
        raise MergeConflict(", ".join(stale))
    commit = make_commit(lane, author, message, drafts, criticality)
    for change in commit.changes:
        lane.graph.put(change.node_type, change.node_id, change.version, commit.commit_id, {CLOSED: True} if change.op == "close" else change.fields)
    lane.records.save("commit", commit.commit_id, commit)
    move_head(lane, MAIN, commit.commit_id, "protected", author.id)
    release = ReleaseEvent(release_id=lane.new_id("rel"), commit_id=commit.commit_id, branch=MAIN, released_at=lane.now,
                           changed_nodes=[VersionRef(id=c.node_id, version=c.version, branch=MAIN, commit_id=commit.commit_id) for c in commit.changes])
    lane.bus.publish("graph.released", "graph.released", release, "versioner")
    count("s14.released")
    log_event("S14", "released", commit_id=commit.commit_id, changes=len(commit.changes), criticality=criticality)
    return commit


def draft_on_branch(lane, author: CommitAuthor, message: str, drafts: list[Draft], criticality: Criticality, branch: str) -> Commit:
    """A change request's commit: kept on its own branch, not written to the graph until it merges."""
    ensure_main(lane)
    commit = make_commit(lane, author, message, drafts, criticality, branch)
    lane.records.save("commit", commit.commit_id, commit)
    move_head(lane, branch, commit.commit_id, "open", author.id, message)
    return commit


def on_release(lane, envelope) -> None:
    """S5's side of a release: a changed knowledge item is embedded again, so search reads the released version."""
    release = ReleaseEvent.model_validate(envelope.payload)
    commit = lane.records.load("commit", release.commit_id) or {"changes": []}
    knowledge = [c for c in commit["changes"] if c["node_type"] == "knowledge" and c["op"] != "close"]
    tag = item_tags.tagger(lane.seed, lane.entities)  # a released item keeps its domain and is tagged again by its new text
    items = [tag({key: value for key, value in c["fields"].items() if key != "_ref"}) for c in knowledge]
    if not items:
        return
    for item, vector in zip(items, lane.embed([item["text"] for item in items], "document")):
        lane.chunks.replace(item, vector)
