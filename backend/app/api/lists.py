# lists.py: the console resources that need more than one record: tenant, clusters, filtered lists, the decision
# pre-check, sensors from connectors, and K11 as LiveEvent. Used by: routes.py, tests. Uses: views.py, ui_models.py, stages_decide.py.
from datetime import datetime

from app.api import ui_models as ui
from app.api import ui_models_work as work
from app.api import views
from app.api.versions_views import approval_of
from app.pipeline import stages_decide
from app.pipeline.observe import read_count, read_last_seen
from app.pipeline.contracts_run import ApprovalRequest, Decision

# Config
LIVE_RESOURCES = {"run.updated": ["runs", "escalations"], "approval.created": ["approvals", "escalations"], "approval.decided": ["approvals", "escalations", "runs"]}


def tenant_view(lane, hq: dict) -> dict:
    policy = lane.seed["refund_policy"]
    thresholds = ui.Thresholds(refund_auto_limit_minor=policy["auto_limit"]["amount_minor"], write_off_limit_minor=0, goodwill_credit_limit_minor=0,
                               l2_approval_ceiling=2, cooling_period_hours_c4=24, approval_expiry_hours=72)
    return ui.Tenant(**hq["tenant"], clusters=[cluster["id"] for cluster in hq["clusters"]], criticality_thresholds=thresholds, is_scale_demo=False).ui()


def clusters_view(lane, hq: dict) -> list[dict]:
    runs = lane.records.list_kind("run")
    escalated = [run for run in runs if run["outcome"] in ("escalated", "awaiting_approval")]
    connectors = [cid for cid, c in lane.seed["connectors"].items() if isinstance(c, dict) and c["grant_active"]]
    return [ui.Cluster(id=c["id"], tenant_id=lane.seed["tenant_id"], name=c["name"], description=c["description"], status="active", connectors=connectors,
                       dri=c["dri"], health=1.0, autonomy_rate=sum(not r["human_touch"] for r in runs) / len(runs) if runs else 0.0,
                       escalation_rate=len(escalated) / len(runs) if runs else 0.0, money_at_stake_minor=0, open_risks=0,
                       cost_per_task_usd=sum(r["cost"]["usd_micro"] for r in runs) / len(runs) / 1_000_000 if runs else 0.0).ui() for c in hq["clusters"]]


def sensors_view(lane, hq: dict, started: datetime) -> list[dict]:
    """One sensor per connector named in hq_tenant.json: health from its grant, activity from S1's counters."""
    hours = max((lane.now - started).total_seconds() / 3600, 1.0)
    shown = []
    for connector_id, about in hq.get("sensors", {}).items():
        connector = lane.seed["connectors"][connector_id]
        captured = read_count(f"s1.captured.{connector_id}")
        shown.append(work.Sensor(id=connector_id, tenant_id=lane.seed["tenant_id"], cluster_id=about["cluster"], name=about["name"], source=connector["source_type"],
                               kind=about["kind"], events=about["events"], subscribers=about["subscribers"], health="ok" if connector["grant_active"] else "down",
                               scopes=[connector["grant_id"]], retention_days=90, personal_data=about["personal_data"],
                               last_event_at=read_last_seen(f"s1.last_event.{connector_id}") or started.isoformat(), events_per_hour=round(captured / hours, 2)).ui())
    return shown


def list_view(lane, resource: str, query: dict) -> list[dict] | None:
    """The served lists, filtered as the console asks. None means this list is not served yet."""
    if resource == "runs":
        runs = sorted(lane.records.list_kind("run"), key=lambda run: run["steps"][0]["started_at"] if run["steps"] else "", reverse=True)
        shown = [views.run_view(lane, run).ui() for run in runs]
        shown = [r for r in shown if (not query.get("status") or r["status"] == query["status"]) and (not query.get("agentId") or r["agentId"] == query["agentId"])]
        return shown[: int(query["limit"])] if query.get("limit") else shown
    if resource == "escalations":
        return [r for r in list_view(lane, "runs", {}) if r["status"] in ("escalated", "awaiting_approval")]
    if resource == "approvals":
        return [approval_of(lane, approval) for approval in lane.records.list_kind("approval")]
    if resource == "access-decisions":
        shown = [views.access_view(lane, entry).ui() for entry in views.audit_entries(lane, "access.decisions")]
        return [a for a in shown if (not query.get("principal") or a["principal"] == query["principal"]) and (not query.get("decision") or a["decision"] == query["decision"])]
    if resource == "audit":
        shown = [views.audit_view(lane, entry).ui() for entry in views.audit_entries(lane)]
        return [a for a in shown if (not query.get("correlation") or a["correlationId"] == query["correlation"]) and a["criticality"] >= int(query.get("minCriticality", 0))]
    return None


def refusal_for(lane, approval_id: str, decision: Decision) -> tuple[int, str] | None:
    """Check a decision before it goes on the bus, so the console hears no at once: (status, reason) or None."""
    approval = lane.records.load("approval", approval_id)
    if approval is None:
        return 404, "unknown_approval"
    run = lane.records.load("run", approval["subject"]["ref"].split(":")[0])
    if run is None or run["outcome"] != "awaiting_approval":
        return 409, "approval_closed"
    delegated = [d["delegated_to"] for d in lane.records.history("decision", approval_id) if d["decision"] == "delegate"]
    state = stages_decide.ApprovalState(request=ApprovalRequest.model_validate(approval), assignee=delegated[-1] if delegated else approval["dri_id"], expires_after_seconds=0)
    reason = stages_decide.refusal(decision, state, lane.seed["people"], run["agent_id"])
    return (409, reason) if reason else None


def live_event(lane, event: dict) -> dict:
    """K11 as the console's LiveEvent: which lists to refetch, and a one-line summary."""
    resources = LIVE_RESOURCES.get(event["type"], []) + ([f"runs/{event['id']}"] if event["type"] == "run.updated" else [])
    summary = " · ".join(str(value) for value in event["display"].values())
    return {"type": event["type"], "tenantId": lane.seed["tenant_id"], "at": event["at"], "resources": resources, "summary": summary}
