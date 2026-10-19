# studio_apply.py: the two Studio operations the console calls. studioApply reviews the change again on the server, then
# applies it through S14 when the person may (low risk, inside their ceiling), or opens a change request for approval.
# studioSuggest lets anyone, L3 included, pass a reviewed change to the workflow DRI; nothing changes until they act.
# Used by: routes.py (ops/studioApply, ops/studioSuggest). Uses: studio_review.py, studio_changes.py, studio_approvals.py.
from app.api.studio_approvals import open_change
from app.api.studio_changes import commit_change, drafts_of, notify
from app.api.studio_draft import StudioError
from app.api.studio_review import review
from app.api.studio_state import Studio
from app.pipeline.stages_version import MergeConflict


def apply_op(lane, person_id: str, body: dict) -> dict:
    change, note = body.get("input") or {}, body.get("note") or ""
    person = lane.seed["people"].get(person_id)
    if person is None:
        raise StudioError("Unknown person", 401)
    if person["tier"] == "L3":
        raise StudioError("L3 can view workflows and suggest edits, but cannot change them.", 403)
    st = Studio.of(lane)
    proposal = review(lane, person_id, change, st)
    rv = proposal["review"]
    if rv["verdict"] == "breaking" and not body.get("acknowledgeBreaking"):
        raise StudioError("The Edit Review Agent marked this breaking. Read the review and confirm before sending it.", 409)
    if rv["authority"]["route"] != "apply":
        return open_change(lane, person_id, change, proposal, note)
    drafts, before, after, flow = drafts_of(lane, st, person_id, change)
    try:
        revision_id = commit_change(lane, person_id, change, proposal, drafts, before, after, None)
    except MergeConflict:
        raise StudioError("Someone changed this a moment ago. Open it again and redo the change.", 409) from None
    target = after or before
    where = f" in {flow['name']}" if flow and change["kind"] != "workflow" else ""
    return {"status": "applied", "targetId": target["id"], "revisionId": revision_id, "changeRequestId": None, "message": f"Applied. {target['name']} is now live{where}."}


def suggest_op(lane, person_id: str, body: dict) -> dict:
    change, note = body.get("input") or {}, body.get("note") or ""
    if person_id not in lane.seed["people"]:
        raise StudioError("Unknown person", 401)
    st = Studio.of(lane)
    proposal = review(lane, person_id, change, st)
    flow = st.flows.get(change.get("targetId") if change.get("kind") == "workflow" else change.get("workflowId"))
    to = (flow or {}).get("dri")
    rv = proposal["review"]
    name = lane.seed["people"][person_id].get("name", person_id)
    notify(lane, to, f"Suggested edit for {(flow or {}).get('name', 'a shared tool')}",
           f"{name} suggests: {proposal['title']}. Review verdict: {rv['verdict']}, C{rv['criticality']}." + (f" Note: {note}" if note else ""), f"/studio?wf={(flow or {}).get('id', '')}")
    to_name = lane.seed["people"].get(to, {}).get("name", "the DRI")
    return {"status": "suggested", "message": f"Sent to {to_name} as a suggestion. They can confirm it from the studio."}
