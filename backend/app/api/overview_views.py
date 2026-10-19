# overview_views.py: the Brain overview for Finebase HQ: the map (clusters and Studio's workflows, with their parts and
# health) and the live numbers beside it. With no runs yet the numbers are zero, but the
# map still draws, so the brain looks alive from the first day. Used by: graph_map.py (graph_resource), tests.
# Uses: lists.py (runs as the console sees them), graph_views.py (agents), studio_state.py and studio_findings.py (workflows).
from datetime import datetime, timedelta

from app.api.graph_views import agents_view
from app.api.studio_findings import health
from app.api.studio_state import Studio
from app.api.lists import list_view
from app.api.ready_views import obligations_view, requests_view, risks_view

# Config
TREND_DAYS = 14
SLOT_MINUTES, SLOTS = 30, 48  # the run series: 30 minute slots over 24 hours


def done(runs: list[dict]) -> list[dict]:
    return [run for run in runs if run["status"] != "running"]


def rates(runs: list[dict]) -> dict:
    finished = done(runs)
    resolved = [run for run in finished if run["status"] == "succeeded"]
    autonomous = [run for run in resolved if not run["humanTouch"]]
    escalated = [run for run in finished if run["status"] == "escalated" or run["humanTouch"]]
    cost = sum(run["costUsd"] for run in finished)
    return {"autonomyRate": len(autonomous) / len(finished) if finished else 0.0, "escalationRate": len(escalated) / len(finished) if finished else 0.0,
            "costPerResolvedUsd": round(cost / len(resolved), 3) if resolved else 0.0}


def started(run: dict) -> datetime | None:
    return datetime.fromisoformat(run["startedAt"].replace("Z", "+00:00")) if run["startedAt"] else None  # Python 3.10 cannot read a trailing Z


def kpi_of(lane, cluster_id: str, runs: list[dict]) -> dict:
    recent = [run for run in runs if (at := started(run)) and lane.now - at < timedelta(days=1)]
    return {"clusterId": cluster_id, "runs24h": len(recent), **rates(runs), "moneyAtStakeMinor": 0, "openRisks": 0, "health": 1.0}


# --- The map

def workflows_of(lane, hq: dict) -> list[dict]:
    """Studio's workflows with their parts and health, so a Studio edit shows on the map."""
    st = Studio.of(lane)
    shown = []
    for flow in st.flows.values():
        found = health(st, flow)["findings"]
        items = [{"id": i["id"], "kind": i["kind"], "name": i["name"], "description": i["description"], "status": i["status"],
                  "shared": i["kind"] == "tool" and len(st.using_tool(i["id"])) > 1} for i in st.scope(flow)]
        shown.append({"id": flow["id"], "name": flow["name"], "description": flow["description"], "clusterId": flow["clusterId"], "status": flow["status"],
                      "criticality": flow["criticality"], "dri": flow["dri"], "items": items,
                      "health": {"breaks": sum(f["severity"] == "break" for f in found), "warnings": sum(f["severity"] == "warn" for f in found)}})
    return shown


def brain_map(lane, hq: dict) -> dict:
    runs = list_view(lane, "runs", {})
    clusters = [{"id": c["id"], "name": c["name"], "description": c["description"], "status": "active", "dri": c["dri"], "health": 1.0,
                 "kpi": {key: value for key, value in kpi_of(lane, c["id"], runs).items() if key not in ("clusterId", "health")}} for c in hq["clusters"]]
    return {"clusters": clusters, "workflows": workflows_of(lane, hq)}


# --- The numbers

def entity_counts(lane) -> dict:
    """Entity protection at a glance (step 16): obligations red and amber, risks on the register, evidence requests still open."""
    statuses = [ob["status"] for ob in obligations_view(lane)]
    open_requests = sum(r["status"] == "open" for r in requests_view(lane))
    return {"red": statuses.count("red"), "amber": statuses.count("amber"), "risks": len(risks_view(lane)), "evidenceOpen": open_requests}


def overview(lane, hq: dict) -> dict:
    runs = list_view(lane, "runs", {})
    kpis = [kpi_of(lane, c["id"], runs) for c in hq["clusters"]]
    agents = agents_view(lane, hq)
    approvals = list_view(lane, "approvals", {})
    days = [(lane.now - timedelta(days=TREND_DAYS - 1 - i)).date().isoformat() for i in range(TREND_DAYS)]
    trend = []
    for day in days:
        mine = [run for run in done(runs) if run["startedAt"][:10] == day]
        trend.append({"day": day, "runs": len(mine), "autonomy": rates(mine)["autonomyRate"], "escalation": rates(mine)["escalationRate"]})
    slot_start = lane.now - timedelta(minutes=SLOT_MINUTES * SLOTS)
    series = [{"at": (slot_start + timedelta(minutes=SLOT_MINUTES * (i + 1))).isoformat(),
               "runs": sum(1 for run in runs if (at := started(run)) and slot_start + timedelta(minutes=SLOT_MINUTES * i) <= at < slot_start + timedelta(minutes=SLOT_MINUTES * (i + 1)))} for i in range(SLOTS)]
    windows = [(0, 7), (7, 14), (0, 30), (30, 60)]  # days back: this week, last week, this month, last month
    costs = [sum(run["costUsd"] for run in runs if (at := started(run)) and timedelta(days=lower) <= lane.now - at < timedelta(days=upper)) for lower, upper in windows]
    connectors = {c["source_type"] for c in lane.seed["connectors"].values() if isinstance(c, dict) and c.get("grant_active")}
    legibility = [{"activity": rule["description"], "clusterId": lane.seed["cluster_id"], "agent": next((a["name"] for a in agents if a["id"] == rule["agent_id"]), rule["agent_id"]),
                   "sensed": any(channel in connectors for channel in rule["channels"]), "skilled": True,
                   "governed": any(rule["skill_id"] in label.get("skills", []) for label in hq["graph_labels"]["policies"].values()), "reported": True}
                  for rule in lane.graph.latest("resolver_rule")]
    return {
        "kpis": kpis,
        "totals": {"runs24h": sum(k["runs24h"] for k in kpis), **rates(runs), "moneyAtStakeMinor": 0, "openRisks": 0,
                   "pendingApprovals": sum(a["status"] == "pending" for a in approvals), "activeAgents": sum(a["status"] == "working" for a in agents)},
        "legibility": legibility, "trend": trend, "runSeries": series, "runningNow": sum(run["status"] == "running" for run in runs),
        "costs": {"weekUsd": costs[0], "prevWeekUsd": costs[1], "monthUsd": costs[2], "prevMonthUsd": costs[3]},
        "entity": entity_counts(lane),
    }
