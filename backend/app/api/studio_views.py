# studio_views.py: the Workflow Studio screens on Finebase HQ: workflow summaries with health and pending counts, one
# workflow with its members and shared tools, its health check, the shared tool library, item history, changes waiting
# for approval, and the notices Studio sends. Used by: graph_map.py (graph_resource). Uses: studio_state.py, studio_findings.py.
from app.api.studio_changes import ChangeRecord
from app.api.studio_findings import health
from app.api.studio_model import MEMBER_KINDS
from app.api.studio_state import Studio

# Config
MOST_REVISIONS = 200
PENDING_STATUS = {"awaiting_approval": "awaiting_approval", "approved": "awaiting_approval", "merged": "applied"}  # the rest show as rejected


def summaries(lane) -> list[dict]:
    st = Studio.of(lane)
    waiting = [ChangeRecord.model_validate(r) for r in lane.records.list_kind("change_request")]
    shown = []
    for flow in st.flows.values():
        counts = {kind: 0 for kind in MEMBER_KINDS}
        for member in st.members(flow):
            counts[member["kind"]] += 1
        counts["tool"] = len(st.tool_ids(flow))
        found = health(st, flow)["findings"]
        shown.append({**flow, "counts": counts, "health": {"breaks": sum(f["severity"] == "break" for f in found), "warnings": sum(f["severity"] == "warn" for f in found)},
                      "pending": sum(r.workflow_id == flow["id"] and r.status in ("awaiting_approval", "approved") for r in waiting)})
    return shown


def detail(lane, flow_id: str) -> dict | None:
    st = Studio.of(lane)
    flow = st.flows.get(flow_id)
    if flow is None:
        return None
    return {"workflow": flow, "items": st.scope(flow),
            "sharedToolUse": [{"toolId": tool_id, "workflows": [{"id": w["id"], "name": w["name"]} for w in st.using_tool(tool_id)]} for tool_id in st.tool_ids(flow)]}


def health_view(lane, flow_id: str) -> dict | None:
    st = Studio.of(lane)
    return health(st, st.flows[flow_id]) if flow_id in st.flows else None


def tools_view(lane) -> list[dict]:
    st = Studio.of(lane)
    return [{"tool": item, "workflows": [{"id": w["id"], "name": w["name"]} for w in st.using_tool(item["id"])]} for item in st.items.values() if item["kind"] == "tool"]


def revisions_view(lane, query: dict) -> list[dict]:
    shown = [{**r, "at": str(r["at"])} for r in lane.records.list_kind("revision")]
    if query.get("target"):
        shown = [r for r in shown if r["targetId"] == query["target"]]
    elif query.get("workflow"):
        shown = [r for r in shown if r["workflowId"] == query["workflow"]]
    return sorted(shown, key=lambda r: r["at"], reverse=True)[:MOST_REVISIONS]


def pending_view(lane) -> list[dict]:
    records = [ChangeRecord.model_validate(r) for r in lane.records.list_kind("change_request") if r["kind"] != "fact"]  # Studio's own changes only
    return [{"id": r.cr_id, "changeRequestId": r.cr_id, "workflowId": r.workflow_id, "input": r.input, "title": r.title, "verdict": r.proposal["review"]["verdict"],
             "criticality": r.criticality, "by": r.drafter, "at": r.created_at.isoformat(), "status": PENDING_STATUS.get(r.status, "rejected")}
            for r in sorted(records, key=lambda r: r.created_at, reverse=True)]


def notifications_view(lane) -> list[dict]:
    notices = sorted(lane.records.list_kind("notification"), key=lambda n: str(n["at"]), reverse=True)
    return [{**n, "tenantId": lane.seed["tenant_id"], "at": str(n["at"])} for n in notices]
