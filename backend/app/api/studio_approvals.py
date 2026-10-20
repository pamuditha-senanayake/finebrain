# studio_approvals.py: Studio changes that need a person. The change waits as a draft commit on its own branch with an
# S8 approval (K8). Decisions follow S8's rules (who may approve, nobody approves their own change, C4 needs two
# leaders and a cooling period); an approval merges it through S14, unless a node moved on (a conflict).
# Used by: studio_apply.py, routes.py, hq.py (sweep). Uses: studio_changes.py, stages_decide.py, stages_version.py.
from datetime import timedelta

from app.api.studio_changes import CR_KIND, ChangeRecord, commit_change, drafts_of, notify
from app.api.studio_state import Studio
from app.pipeline import stages_decide, stages_version
from app.pipeline.contracts_graph import CommitAuthor
from app.pipeline.contracts_run import ApprovalRequest, ApprovalSubject, Approvers, Decision
from app.pipeline.observe import log_event
from app.pipeline.stages_govern import C4_COOLING_HOURS

# Config
APPROVERS = {2: Approvers(tier="L2", count=1, roles=["steward"]), 3: Approvers(tier="L1", count=1, roles=["dri", "leader"]),
             4: Approvers(tier="L1", count=2, roles=["leader"])}
DUE_HOURS = 72


def open_change(lane, person_id: str, change: dict, proposal: dict, note: str) -> dict:
    """Draft the commit on a branch, open the approval, and tell the DRI."""
    drafts, before, after, flow = drafts_of(lane, Studio.of(lane), person_id, change)
    level = max(2, proposal["review"]["criticality"])
    cr_id = lane.new_id("cr")
    branch = f"studio/{cr_id}"
    commit = stages_version.draft_on_branch(lane, CommitAuthor(kind="studio", id=person_id), proposal["title"], drafts, level, branch)
    dri = (flow or {}).get("dri") or person_id
    due = lane.now + timedelta(hours=DUE_HOURS)
    approval = ApprovalRequest(approval_id=lane.new_id("apr"), subject=ApprovalSubject(kind="change_request", ref=cr_id), criticality=level,
                               summary_plain=f"{proposal['title']}. {proposal['review']['summary']}", diff_ref=commit.commit_id, evidence_refs=[],
                               required_approvers=APPROVERS[level], dri_id=dri, due_at=due, expires_at=due)
    lane.records.save("change_request", cr_id, ChangeRecord(
        cr_id=cr_id, title=proposal["title"], kind=CR_KIND[change["kind"]], workflow_id=(flow or {}).get("id"), input=change, proposal=proposal, drafts=drafts,
        commit_id=commit.commit_id, branch=branch, approval_id=approval.approval_id, status="awaiting_approval", drafter=person_id, dri=dri, criticality=level,
        created_at=lane.now, note=note, before=before, after=after))
    lane.records.save("approval", approval.approval_id, approval)  # visible at once; the bus copy is for the audit log
    lane.bus.publish("approvals.requested", "approval.requested", approval, "studio")
    if dri != person_id:
        notify(lane, dri, f"Studio change for {(flow or {}).get('name', 'a shared tool')}", f"{proposal['title']}. Review verdict: {proposal['review']['verdict']}.", f"/l1/approvals/{approval.approval_id}", "approval")
    approver = proposal["review"]["authority"]["approver"]
    return {"status": "routed", "targetId": change.get("targetId") or cr_id, "revisionId": None, "changeRequestId": cr_id,
            "message": f"Sent to {approver} as change request {cr_id}. It applies when approved."}


def state_of(lane, approval: dict, record: ChangeRecord) -> stages_decide.ApprovalState:
    delegated = [d["delegated_to"] for d in lane.records.history("decision", approval["approval_id"]) if d["decision"] == "delegate"]
    return stages_decide.ApprovalState(request=ApprovalRequest.model_validate(approval), assignee=delegated[-1] if delegated else record.dri,
                                       expires_after_seconds=0, approved_by=record.approved_by)


def change_of(lane, approval: dict | None) -> ChangeRecord | None:
    if not approval or approval["subject"]["kind"] != "change_request":
        return None
    stored = lane.records.load("change_request", approval["subject"]["ref"])
    return ChangeRecord.model_validate(stored) if stored else None


def refusal_for(lane, approval: dict, decision: Decision) -> tuple[int, str] | None:
    """The console's quick check before a decision goes on the bus."""
    record = change_of(lane, approval)
    if record is None or record.status != "awaiting_approval":
        return 409, "approval_closed"
    reason = stages_decide.refusal(decision, state_of(lane, approval, record), lane.seed["people"], record.drafter)
    return (409, reason) if reason else None


def on_decision(lane, envelope) -> None:
    """The Studio side of approvals.decided: count, merge, or close the change."""
    decision = Decision.model_validate(envelope.payload)
    approval = lane.records.load("approval", decision.approval_id)
    record = change_of(lane, approval)
    if record is None or record.status != "awaiting_approval" or refusal_for(lane, approval, decision):
        return
    if decision.decision == "approve":
        state = state_of(lane, approval, record)
        enough = stages_decide.count_approvals(state, decision)
        record = record.model_copy(update={"approved_by": state.approved_by})
        if enough and record.criticality >= 4:
            seconds = C4_COOLING_HOURS * lane.seed.get("approval_timing", {}).get("seconds_per_cooling_hour", 3600)  # the same clock S8 uses
            record = record.model_copy(update={"status": "approved", "cooling_until": lane.now + timedelta(seconds=seconds)})
        elif enough:
            record = merge(lane, record)
    elif decision.decision in ("reject", "request_changes"):
        record = record.model_copy(update={"status": "rejected" if decision.decision == "reject" else "changes_requested"})
        stages_version.move_head(lane, record.branch, record.commit_id, "abandoned", decision.decided_by[0])
    save(lane, record)


def merge(lane, record: ChangeRecord) -> ChangeRecord:
    """S14 merges the approved drafts to main. A node that moved on since the draft makes it a conflict instead."""
    try:
        commit_change(lane, record.drafter, record.input, record.proposal, record.drafts, record.before, record.after, record.cr_id)
    except stages_version.MergeConflict as error:
        log_event("S14", "merge_conflict", cr_id=record.cr_id, nodes=str(error))
        return record.model_copy(update={"status": "conflict"})
    stages_version.move_head(lane, record.branch, record.commit_id, "merged", record.drafter)
    return record.model_copy(update={"status": "merged", "merged_at": lane.now})


def sweep(lane) -> None:
    """Merge C4 changes whose cooling period has ended. Called by the HQ loop."""
    for stored in lane.records.list_kind("change_request"):
        record = ChangeRecord.model_validate(stored)
        if record.status == "approved" and record.cooling_until and record.cooling_until <= lane.now:
            save(lane, merge(lane, record))


def save(lane, record: ChangeRecord) -> None:
    """Save the change, unless it already merged: a second delivery of the same decision must not undo a merge."""
    stored = lane.records.load("change_request", record.cr_id)
    if stored and stored["status"] == "merged" and record.status != "merged":
        log_event("S14", "merged_change_kept", cr_id=record.cr_id, refused=record.status)
        return
    lane.records.save("change_request", record.cr_id, record)
