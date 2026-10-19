# graph_views.py: the 9c read-only screens for agents, skills and resolver rules. Each comes from the graph that
# S3, S5 and S7 already read, with names from hq_tenant.json and live numbers from the run records.
# Used by: routes.py, graph_map.py, tests/test_api_graph.py. Uses: ui_models_graph.py, ui_models.py.
from datetime import datetime, timedelta

from app.api import ui_models_graph as g
from app.api.ui_models import VersionRef

# Config
ACCESS_BY_TIER = {"L1": "restricted", "L2": "restricted", "L3": "confidential"}  # the highest sensitivity each tier reads
WORKING_WINDOW = timedelta(minutes=5)  # an agent with a run this recent shows as working


def place_in_document(item: dict) -> tuple[str, int]:
    """Where an item sits in its source, so a policy reads in the document's own order."""
    span = item["source"].get("span") or "0:0"
    return item["source"]["document_id"], int(span.split(":")[0])


# --- Run numbers

def runs_where(lane, field: str, value: str) -> list[dict]:
    """Runs whose agent_id, or skill id, matches."""
    runs = lane.records.list_kind("run")
    return [run for run in runs if (run["skill_ref"]["id"] if field == "skill" else run["agent_id"]) == value]


def started(run: dict) -> datetime | None:
    # Python 3.10 cannot read a trailing Z, and runs recorded through Temporal store one
    return datetime.fromisoformat(str(run["steps"][0]["started_at"]).replace("Z", "+00:00")) if run["steps"] else None


def share(runs: list[dict], outcome: str) -> float:
    return sum(run["outcome"] == outcome for run in runs) / len(runs) if runs else 0.0


# --- Agents

def agent_view(lane, hq: dict, agent: dict) -> g.Agent:
    agent_id = agent["_ref"]["id"]
    about = hq["graph_labels"]["agents"].get(agent_id, {})
    rules = [rule for rule in lane.graph.latest("resolver_rule") if rule["agent_id"] == agent_id]
    skills = {skill["_ref"]["id"]: skill for skill in lane.graph.latest("skill")}
    runs = runs_where(lane, "agent", agent_id)
    recent = [run for run in runs if (at := started(run)) and lane.now - at < timedelta(days=1)]
    today = [run for run in recent if started(run).date() == lane.now.date()]
    policies = [key for key, label in hq["graph_labels"]["policies"].items() if any(rule["skill_id"] in label.get("skills", []) for rule in rules)]
    return g.Agent(
        id=agent_id, tenant_id=lane.seed["tenant_id"], name=about.get("name", agent_id), kind=about.get("kind", "worker"), tier=agent["tier"],
        cluster_id=lane.seed["cluster_id"], description=about.get("description", ""), autonomy="supervised",
        skills=[VersionRef(**{key: skills[rule["skill_id"]]["_ref"][key] for key in ("id", "version", "branch")}) for rule in rules if rule["skill_id"] in skills],
        capabilities=agent["capabilities"], access_level=ACCESS_BY_TIER[agent["tier"]], sensors=[], templates=[], policies=policies,
        status="working" if any(lane.now - started(run) < WORKING_WINDOW for run in recent) else "idle", work_kind=None,
        dri=about.get("dri", ""), queue_depth=sum(run["outcome"] == "awaiting_approval" for run in runs), throughput_per_hour=round(len(recent) / 24, 2),
        error_rate=share(runs, "failed"), cost_today_usd=sum(run["cost"]["usd_micro"] for run in today) / 1_000_000, task_success=share(runs, "resolved"),
        training=[],
    )


def agents_view(lane, hq: dict) -> list[dict]:
    return [agent_view(lane, hq, agent).ui() for agent in lane.graph.latest("agent")]


# --- Skills

def step_kind(text: str, tools: list[str]) -> tuple[str, str | None]:
    """A step that names a tool is a tool step; one that reads the documents is retrieval; the rest is judgment."""
    tool = next((tool for tool in tools if tool in text), None)
    return ("tool", tool) if tool else ("retrieval", None) if "documents" in text else ("judgment", None)


def skill_view(lane, hq: dict, skill: dict) -> g.Skill:
    ref = skill["_ref"]
    rules = [rule for rule in lane.graph.latest("resolver_rule") if rule["skill_id"] == ref["id"]]
    runs = runs_where(lane, "skill", ref["id"])
    steps = [g.SkillStep(id=f"{ref['id']}-{i}", kind=step_kind(text, skill["allowed_tools"])[0], text=text, tool=step_kind(text, skill["allowed_tools"])[1])
             for i, text in enumerate(skill["steps"], start=1)]
    success = share(runs, "resolved")
    return g.Skill(
        id=ref["id"], tenant_id=lane.seed["tenant_id"], name=skill["name"], version=ref["version"], branch=ref["branch"], status="active",
        cluster_id=lane.seed["cluster_id"], trigger=" · ".join(rule["description"] for rule in rules) or "Not routed yet",
        inputs=sorted({entity for rule in rules for entity in rule["required_entities"]}), steps=steps, tools=skill["allowed_tools"],
        policies=[key for key, label in hq["graph_labels"]["policies"].items() if ref["id"] in label.get("skills", [])],
        required_capabilities=sorted({cap for agent in lane.graph.latest("agent") if any(r["agent_id"] == agent["_ref"]["id"] for r in rules) for cap in agent["capabilities"]}),
        outputs=[tool for tool in skill["allowed_tools"] if tool != "escalate"], template_fields=[],
        eval_suite={"id": f"eval_{ref['id']}", "cases": 0, "passRate": 0.0},
        health={"taskSuccess": success, "consistencyPassK": 0.0, "k": 0, "conformance": success},
        agent_ids=sorted({rule["agent_id"] for rule in rules}), dri=hq["graph_labels"]["skill_dri"], updated_at=lane.now.isoformat(), origin="authored",
    )


def skills_view(lane, hq: dict, skill_id: str | None = None) -> list[dict]:
    """Every skill, or the versions of one (only the newest is stored until S14 writes history)."""
    return [skill_view(lane, hq, skill).ui() for skill in lane.graph.latest("skill") if skill_id in (None, skill["_ref"]["id"])]


# --- Resolver rules

def resolver_view(lane) -> list[dict]:
    skills = {skill["_ref"]["id"]: skill["_ref"] for skill in lane.graph.latest("skill")}
    shown = []
    for rule in lane.graph.latest("resolver_rule"):
        runs = runs_where(lane, "skill", rule["skill_id"])
        last = max((started(run) for run in runs if started(run)), default=lane.now)
        words = ", ".join(rule["keywords"])
        needs = f" · needs {', '.join(rule['required_entities'])}" if rule["required_entities"] else ""
        ref = skills.get(rule["skill_id"], {"id": rule["skill_id"], "version": 0, "branch": "main"})
        shown.append(g.ResolverRule(
            id=rule["rule_id"], tenant_id=lane.seed["tenant_id"], event=", ".join(rule["kinds"]), match=f"{rule['description']} ({words}{needs})",
            skill=VersionRef(id=ref["id"], version=ref["version"], branch=ref["branch"]), agent_id=rule["agent_id"], priority=rule["priority"],
            trigger_eval={"cases": len(runs), "passRate": share(runs, "resolved"), "lastRunAt": last.isoformat()},
        ).ui())
    return shown
