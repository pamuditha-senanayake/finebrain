# studio_changes.py: what a confirmed Studio change leaves behind. The drafts S14 commits (the target, plus the workflow
# when a member joins or leaves), a revision for the item's history, and notices for the people who must know.
# Used by: studio_apply.py, studio_approvals.py, studio_views.py. Uses: studio_draft.py, studio_model.py, stages_version.py.
from datetime import datetime

from pydantic import BaseModel

from app.api.studio_draft import materialize, snapshot
from app.api.studio_model import drafts_for
from app.pipeline import stages_version
from app.pipeline.contracts_graph import CommitAuthor
from app.pipeline.stages_version import Draft

# Config
CR_KIND = {"workflow": "fix", "skill": "skill", "policy": "policy", "template": "template", "agent": "security", "tool": "security",
           "sensor": "grant", "scheduler": "fix", "loop": "fix"}


class ChangeRecord(BaseModel):
    """A Studio change waiting for approval, and what became of it."""
    cr_id: str
    title: str
    kind: str
    workflow_id: str | None
    input: dict
    proposal: dict
    drafts: list[Draft]
    commit_id: str
    branch: str
    approval_id: str
    status: str  # awaiting_approval, approved (cooling), merged, rejected, changes_requested, conflict
    drafter: str
    dri: str
    criticality: int
    created_at: datetime
    merged_at: datetime | None = None
    cooling_until: datetime | None = None
    approved_by: list[str] = []
    note: str = ""
    before: dict | None = None  # the target as it was drafted against, and as it will be
    after: dict | None = None


class RevisionRecord(BaseModel):
    """One line of an item's history, in the console's Revision shape."""
    id: str
    targetKind: str
    targetId: str
    workflowId: str | None
    version: int
    op: str
    at: datetime
    by: str
    summary: str
    snapshot: dict | None
    verdict: str | None
    changeRequestId: str | None


class Notice(BaseModel):
    id: str
    to: str | None
    title: str
    body: str
    href: str
    kind: str
    at: datetime
    read: bool = False


def drafts_of(lane, st, person_id: str, change: dict) -> tuple[list[Draft], dict | None, dict | None, dict | None]:
    """The drafts for a change: the target, and its workflow when a member is added or removed."""
    before, after, flow = materialize(st, lane.seed, person_id, change)
    stamp = {"updatedAt": lane.now.isoformat(), "updatedBy": person_id}
    after = {**after, **stamp} if after else None
    drafts = drafts_for(lane, change["kind"], before["id"] if before else None, after)
    if flow and change["kind"] not in ("workflow", "tool"):
        target_id, members = (after or before)["id"], flow["members"]
        moved = members + [target_id] if change["intent"] == "create" else [m for m in members if m != target_id] if change["intent"] == "delete" else members
        if moved != members:
            drafts += drafts_for(lane, "workflow", flow["id"], {**flow, "members": moved, **stamp})
    seen, unique = set(), []
    for draft in drafts:
        if (draft.node_type, draft.node_id) not in seen:
            seen.add((draft.node_type, draft.node_id))
            unique.append(draft)
    return unique, before, after, flow


def commit_change(lane, person_id: str, change: dict, proposal: dict, drafts: list[Draft], before: dict | None, after: dict | None, cr_id: str | None) -> str:
    """S14 applies the drafts to main and releases them; the revision records it for the item's history."""
    commit = stages_version.apply(lane, CommitAuthor(kind="studio", id=person_id), proposal["title"], drafts, proposal["review"]["criticality"])
    target = after or before
    changes = proposal["changes"]
    summary = {"create": f"Created {target['name']}", "delete": f"Deleted {target['name']}"}.get(change["intent"]) \
        or "; ".join(f"{c['label']}: {c['after'] or 'cleared'}" for c in changes[:3]) or proposal["title"]
    version = (before or {}).get("version", 0) + 1
    revision = RevisionRecord(id=f"rev-{target['id']}-v{version}-{commit.commit_id[-6:]}", targetKind=change["kind"], targetId=target["id"],
                              workflowId=target["id"] if change["kind"] == "workflow" else target.get("workflowId"), version=version, op=change["intent"], at=lane.now,
                              by=person_id, summary=summary, snapshot=snapshot(after) if after else None, verdict=proposal["review"]["verdict"], changeRequestId=cr_id)
    lane.records.save("revision", revision.id, revision)
    return revision.id


def notify(lane, to: str | None, title: str, body: str, href: str, kind: str = "info") -> None:
    notice = Notice(id=lane.new_id("nt"), to=to, title=title, body=body, href=href, kind=kind, at=lane.now)
    lane.records.save("notification", notice.id, notice)
