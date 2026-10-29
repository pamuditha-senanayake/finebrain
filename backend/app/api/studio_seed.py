# studio_seed.py: the first Workflow Studio view of Finebase HQ, built into the seed before the graph loads it, so
# versions stay real: Studio metadata is not a change. One workflow per routing rule, with its skill, agent, policies
# and a sensor per channel; tools are shared. From then on Studio and the pipeline read the same nodes.
# Used by: hq.py (load_hq). Uses: studio_model.py (field names, steps), tools.py, stages_govern.py, brain_workflows.py.
from app.api import brain_workflows
from app.api.graph_views import place_in_document
from app.api.studio_model import STUDIO, step_line
from app.pipeline.stages_govern import CAPABILITY_FOR_ACTION
from app.pipeline.tools import TOOLS

# Config
SEEDED_AT = "2026-01-01T00:00:00+05:30"
SIDE_EFFECT = {"issue_refund": "money", "reply_customer": "public", "escalate": "write"}
OPEN_CAPABILITIES = {"escalate"}  # anyone may escalate, so the tool asks for nothing


def meta(node_id: str, kind: str, workflow_id: str | None, name: str, dri: str, fields: dict, description: str = "") -> dict:
    return {"id": node_id, "kind": kind, "workflowId": workflow_id, "name": name, "description": description, "topics": [], "status": "active",
            "dri": dri, "fields": fields, "updatedAt": SEEDED_AT, "updatedBy": "system"}


def statement_of(seed: dict, key: str) -> str:
    items = sorted((k for k in seed["knowledge"] if (k.get("version_ref") or {}).get("id") == key and not k.get("valid_to")), key=place_in_document)
    return " ".join(k["text"] for k in items)


def tool_nodes(skills: list[dict], dri: str) -> list[tuple[str, str, dict]]:
    nodes = []
    for tool in sorted({t for s in skills for t in s["allowed_tools"]}):
        capability = "" if CAPABILITY_FOR_ACTION.get(tool) in OPEN_CAPABILITIES else CAPABILITY_FOR_ACTION.get(tool, "")
        fields = {"level": "prebuilt", "endpoint": TOOLS[tool]["runner"], "capability": capability, "sensitivity": "confidential" if SIDE_EFFECT[tool] == "money" else "internal",
                  "sideEffect": SIDE_EFFECT[tool], "rateLimitPerMin": TOOLS[tool]["rate_per_minute"] or 0, "code": ""}
        nodes.append(("tool", f"tool:{tool}", {STUDIO: meta(f"tool:{tool}", "tool", None, tool.replace("_", " "), dri, fields)}, TOOLS[tool]["version"]))
    return nodes


def extend_seed(seed: dict, hq: dict) -> dict:
    """The seed with a Studio view on every skill, agent and policy, plus tool, sensor and workflow nodes."""
    labels, dri = hq["graph_labels"], hq["graph_labels"]["skill_dri"]
    skills = {s["id"]: dict(s) for s in seed["skills"]}
    agents = {key: dict(a) for key, a in seed["agents"].items()}
    policy = dict(seed["refund_policy"])
    nodes = tool_nodes(list(skills.values()), dri)
    for rule in seed["resolver_rules"]:
        wf_id, skill = f"wf_{rule['activity_id']}", skills[rule["skill_id"]]
        governing = [key for key, label in labels["policies"].items() if rule["skill_id"] in label.get("skills", []) and key == policy["policy_ref"]["id"]]
        siblings = [other for other in seed["resolver_rules"] if other["activity_id"] == rule["activity_id"]]  # one workflow per activity
        channels = {channel for other in siblings for channel in other["channels"]}
        sensors = [conn for conn in hq.get("sensors", {}) if seed["connectors"][conn]["source_type"] in channels]
        sensor_ids = [f"{wf_id}.sensor.{conn}" for conn in sensors]
        for conn, sensor_id in zip(sensors, sensor_ids):
            about = hq["sensors"][conn]
            fields = {"source": seed["connectors"][conn]["source_type"], "sensorKind": about["kind"], "events": about["events"], "feeds": [rule["agent_id"]],
                      "retentionDays": 90, "personalData": about["personal_data"], "health": "ok"}
            nodes.append(("sensor", sensor_id, {STUDIO: meta(sensor_id, "sensor", wf_id, about["name"], dri, fields)}))
        skill[STUDIO] = meta(rule["skill_id"], "skill", wf_id, skill["name"], dri, {
            "trigger": " · ".join(other["description"] for other in siblings), "steps": [step_line(text, skill["allowed_tools"]) for text in skill["steps"]], "agents": [rule["agent_id"]],
            "tools": [f"tool:{t}" for t in skill["allowed_tools"]], "policies": governing, "templates": [], "inputs": sensor_ids,
            "outputs": [t for t in skill["allowed_tools"] if t != "escalate"], "evalCases": 0})
        about = labels["agents"].get(rule["agent_id"], {})
        agents[rule["agent_id"]][STUDIO] = meta(rule["agent_id"], "agent", wf_id, about.get("name", rule["agent_id"]), about.get("dri", dri), {
            "autonomy": "supervised", "capabilities": agents[rule["agent_id"]]["capabilities"], "accessLevel": "confidential", "model": "claude-sonnet-5-5", "maxConcurrent": 2},
            about.get("description", ""))
        for key in governing:
            policy[STUDIO] = meta(key, "policy", wf_id, labels["policies"][key]["name"], labels["policies"][key]["dri"], {
                "statement": statement_of(seed, key), "ruleKind": "refund", "criticality": str(policy["escalation"]["criticality"]), "validFrom": "2026-01-01",
                "param.days": policy["window_days"], "param.amountMinor": policy["auto_limit"]["amount_minor"], "param.currency": policy["auto_limit"]["currency"]})
        workflow = {"id": wf_id, "tenantId": seed["tenant_id"], "name": skill["name"], "description": rule["description"], "topics": [], "status": "active",
                    "clusterId": seed["cluster_id"], "dri": dri, "editors": [], "criticality": 3 if "issue_refund" in skill["allowed_tools"] else 2,
                    "members": [rule["skill_id"], rule["agent_id"], *governing, *sensor_ids], "story": None, "updatedAt": SEEDED_AT, "updatedBy": "system"}
        nodes.append(("workflow", wf_id, {STUDIO: workflow}))
    nodes += brain_workflows.nodes(meta, dri, seed["tenant_id"], seed["cluster_id"], SEEDED_AT)  # Add a document, Meeting tasks
    return {**seed, "skills": list(skills.values()), "agents": agents, "refund_policy": policy, "studio_nodes": nodes}
