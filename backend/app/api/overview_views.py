# overview_views.py: the Brain overview for Finebase HQ: the map (clusters and one workflow per routing rule, with its
# agent, skill, policies and tools) and the live numbers beside it. With no runs yet the numbers are zero, but the
# map still draws, so the brain looks alive from the first day. Used by: graph_map.py (graph_resource), tests.
# Uses: lists.py (runs as the console sees them), graph_views.py (agents), ui_models.py.
from datetime import datetime, timedelta

from app.api.graph_views import agents_view
from app.api.lists import list_view

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
    return datetime.fromisoformat(run["startedAt"]) if run["startedAt"] else None


def kpi_of(lane, cluster_id: str, runs: list[dict]) -> dict:
    recent = [run for run in runs if (at := started(run)) and lane.now - at < timedelta(days=1)]
    return {"clusterId": cluster_id, "runs24h": len(recent), **rates(runs), "moneyAtStakeMinor": 0, "openRisks": 0, "health": 1.0}


# --- The map

def workflows_of(lane, hq: dict) -> list[dict]:
    """One workflow per routing rule: who does it, how, under which rules, with which tools."""
    agents = {a["id"]: a for a in agents_view(lane, hq)}
    skills = {s["_ref"]["id"]: s for s in lane.graph.latest("skill")}
    tool_use = [tool for skill in skills.values() for tool in skill["allowed_tools"]]
    policies = hq["graph_labels"]["policies"]
    shown = []
    for rule in lane.graph.latest("resolver_rule"):
        skill, agent = skills.get(rule["skill_id"]), agents.get(rule["agent_id"])
        items = [{"id": f"agent:{rule['agent_id']}", "kind": "agent", "name": agent["name"] if agent else rule["agent_id"], "description": agent["description"] if agent else "", "status": "active", "shared": False}]
        if skill:
            items.append({"id": f"skill:{rule['skill_id']}", "kind": "skill", "name": skill["name"], "description": " ".join(skill["steps"][:1]), "status": "active", "shared": False})
            items += [{"id": f"tool:{tool}", "kind": "tool", "name": tool.replace("_", " "), "description": "", "status": "active", "shared": tool_use.count(tool) > 1} for tool in skill["allowed_tools"]]
        items += [{"id": f"policy:{key}", "kind": "policy", "name": label.get("name", key), "description": "", "status": "active", "shared": False}
                  for key, label in policies.items() if rule["skill_id"] in label.get("skills", [])]
        shown.append({"id": f"wf_{rule['activity_id']}", "name": skill["name"] if skill else rule["description"], "description": rule["description"], "clusterId": lane.seed["cluster_id"],
                      "status": "active", "criticality": rule["base_criticality"], "dri": agent["dri"] if agent else "", "health": {"breaks": 0, "warnings": 0}, "items": items})
    return shown


def brain_map(lane, hq: dict) -> dict:
    runs = list_view(lane, "runs", {})
    clusters = [{"id": c["id"], "name": c["name"], "description": c["description"], "status": "active", "dri": c["dri"], "health": 1.0,
                 "kpi": {key: value for key, value in kpi_of(lane, c["id"], runs).items() if key not in ("clusterId", "health")}} for c in hq["clusters"]]
    return {"clusters": clusters, "workflows": workflows_of(lane, hq)}


# --- The numbers

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
        "entity": {"red": 0, "amber": 0, "risks": 0, "evidenceOpen": 0},
    }
