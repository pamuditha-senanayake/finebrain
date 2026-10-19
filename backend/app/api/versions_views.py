# versions_views.py: S14 on the console: branches, commits and change requests for Knowledge graph › Versions, and the
# approval of a Studio change request in the same shape as a run's approval, so To review shows both.
# Used by: graph_map.py, lists.py, routes.py. Uses: studio_changes.py, views.py, ui_models.py.
from app.api import grant_views, grants, views
from app.api.studio_changes import ChangeRecord

# Config
OP = {"add": "add", "update": "modify", "close": "remove"}
APPROVAL_STATUS = {"awaiting_approval": "pending", "approved": "approved", "merged": "approved", "changes_requested": "changes_requested"}  # the rest: rejected


def actor(lane, person_id: str) -> dict:
    person = lane.seed["people"].get(person_id)
    return {"kind": "human", "id": person_id, "name": person.get("name", person_id)} if person else {"kind": "system", "id": person_id, "name": person_id}


def branches_view(lane) -> list[dict]:
    return [{"id": b["name"], "tenantId": lane.seed["tenant_id"], "name": b["name"], "env": "production" if b["name"] == "main" else "sandbox", "base": b["base"],
             "head": b["head"], "status": b["status"], "description": b["description"], "createdBy": actor(lane, b["created_by"]), "createdAt": str(b["created_at"])}
            for b in lane.records.list_kind("branch")]


def commit_view(lane, commit: dict) -> dict:
    def label_of(change: dict) -> str:
        return (change["fields"].get("studio") or {}).get("name") or change["fields"].get("name") or change["node_id"]
    return {"id": commit["commit_id"], "tenantId": lane.seed["tenant_id"], "branch": commit["branch"], "parentId": commit["parent_commit_id"],
            "author": actor(lane, commit["author"]["id"]), "message": commit["message"], "criticality": commit["criticality"], "evidence": [],
            "changes": [{"op": OP[c["op"]], "nodeType": c["node_type"], "nodeId": c["node_id"], "label": label_of(c), "field": None, "before": None, "after": f"v{c['version']}"}
                        for c in commit["changes"]],
            "createdAt": str(commit["created_at"]), "tag": None}


def commits_view(lane, query: dict) -> list[dict]:
    commits = [c for c in lane.records.list_kind("commit") if not query.get("branch") or c["branch"] == query["branch"]]
    return [commit_view(lane, c) for c in sorted(commits, key=lambda c: str(c["created_at"]), reverse=True)]


def change_request_view(lane, record: ChangeRecord) -> dict:
    rv, proposal = record.proposal["review"], record.proposal
    plain = [rv["summary"], *(f"{c['label']}: {c['before'] or 'empty'} → {c['after'] or 'empty'}" for c in proposal["changes"]),
             *(f"{'Breaks' if f['severity'] == 'break' else 'Watch'}: {f['text']}" for f in rv["findings"] if f["severity"] != "info"),
             *([f"Note: {record.note}"] if record.note else [])]
    target = record.input.get("targetId") or record.cr_id
    return {"id": record.cr_id, "tenantId": lane.seed["tenant_id"], "title": record.title, "kind": record.kind, "fromBranch": record.branch, "toBranch": "main",
            "commits": [record.commit_id], "plainDiff": plain,
            "changes": [{"op": "modify", "nodeType": f"studio.{record.input['kind']}", "nodeId": target, "label": proposal["targetName"], "field": c["field"],
                         "before": c["before"], "after": c["after"]} for c in proposal["changes"]],
            "impactPreview": proposal.get("impact"), "tests": proposal.get("tests"), "approvalId": record.approval_id, "status": record.status, "criticality": record.criticality,
            "criticalityReasons": [*rv["criticalityReasons"], f"{rv['reviewer']}: {rv['verdict']}"], "drafter": actor(lane, record.drafter), "dri": record.dri,
            "clusters": [lane.seed["cluster_id"]], "createdAt": record.created_at.isoformat(), "mergedAt": record.merged_at.isoformat() if record.merged_at else None,
            "coolingUntil": record.cooling_until.isoformat() if record.cooling_until else None, "correlationId": f"studio:{record.cr_id}"}


def change_requests_view(lane, cr_id: str | None = None) -> list[dict] | dict | None:
    records = [ChangeRecord.model_validate(r) for r in lane.records.list_kind("change_request")]
    if cr_id:
        return next((change_request_view(lane, r) for r in records if r.cr_id == cr_id), None)
    return [change_request_view(lane, r) for r in sorted(records, key=lambda r: r.created_at, reverse=True)]


def approval_of(lane, approval: dict) -> dict:
    """A run's approval as before; a grant's (step 16) and a change request's from their records."""
    if approval["subject"]["kind"] == "grant" and (grant := grants.grant_of(lane, approval)):
        return grant_views.approval_view(lane, approval, grant)
    if approval["subject"]["kind"] != "change_request":
        return views.approval_view(lane, approval).ui()
    stored = lane.records.load("change_request", approval["subject"]["ref"])
    record = ChangeRecord.model_validate(stored) if stored else None
    decisions = lane.records.history("decision", approval["approval_id"])
    delegated = [d["delegated_to"] for d in decisions if d["decision"] == "delegate"]
    return {"id": approval["approval_id"], "tenantId": lane.seed["tenant_id"], "subject": {"kind": "change_request", "id": approval["subject"]["ref"]},
            "title": approval["summary_plain"].split(". ")[0], "summary": approval["summary_plain"], "criticality": approval["criticality"],
            "requiredApprovers": approval["required_approvers"], "dueAt": str(approval["due_at"]), "createdAt": record.created_at.isoformat() if record else str(approval["due_at"]),
            "votes": [{"by": d["decided_by"][0], "at": str(d["decided_at"]), "decision": d["decision"], "comment": d.get("comment", "")} for d in decisions
                      if d["decision"] in ("approve", "reject", "request_changes", "delegate")],
            "status": APPROVAL_STATUS.get(record.status if record else "", "rejected"), "delegatedTo": delegated[-1] if delegated else None, "dri": approval["dri_id"],
            "drafter": actor(lane, record.drafter if record else "system"), "evidence": approval["evidence_refs"], "correlationId": f"studio:{approval['subject']['ref']}"}
