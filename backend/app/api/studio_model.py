# studio_model.py: how Workflow Studio sees the graph, and how one Studio edit becomes graph changes. Each node keeps its
# Studio view under "studio" next to the fields the pipeline reads, and an edit rewrites both: a skill's steps and tools,
# an agent's capabilities, a policy's limits (plus its wording in knowledge, so S6 never reads an old window), and the
# routing rules a paused workflow or skill must stop using. Used by: studio_seed.py, studio_review.py, studio_apply.py, studio_views.py.
from app.api.graph_views import place_in_document, step_kind
from app.pipeline.stages_version import Draft

# Config
STUDIO = "studio"
MEMBER_KINDS = ["sensor", "scheduler", "agent", "skill", "policy", "tool", "template", "loop"]  # the order members are shown in
STEP_KINDS = ("judgment", "tool", "retrieval", "quality_gate")


# --- Steps and wording

def step_line(text: str, tools: list[str]) -> str:
    """A pipeline step as Studio writes it: "kind: text [tool:id]"."""
    kind, tool = step_kind(text, tools)
    return f"{kind}: {text}" + (f" [tool:{tool}]" if tool else "")


def step_text(line: str) -> str:
    """The step as the pipeline reads it: no kind prefix, no tool tag."""
    head, _, rest = line.partition(": ")
    text = rest if head in STEP_KINDS else line
    return text.split(" [tool:")[0].strip()


def policy_statement(lane, key: str) -> str:
    """The policy's current wording: its open knowledge items, in document order."""
    items = [k for k in lane.graph.latest("knowledge") if (k.get("version_ref") or {}).get("id") == key and not k.get("valid_to")]
    items.sort(key=place_in_document)
    return " ".join(k["text"] for k in items)


# --- Reading

def view(node: dict) -> dict:
    return {**node[STUDIO], "version": node["_ref"]["version"]}


def items(lane) -> list[dict]:
    return [view(node) for kind in MEMBER_KINDS for node in lane.graph.latest(kind) if STUDIO in node]


def workflows(lane) -> list[dict]:
    return [{"story": None, **view(node)} for node in lane.graph.latest("workflow")]


def node_of(lane, kind: str, node_id: str | None) -> dict | None:
    return next((node for node in lane.graph.latest(kind) if node["_ref"]["id"] == node_id), None) if node_id else None


# --- Writing: one Studio change to the drafts S14 commits

def drafts_for(lane, kind: str, target_id: str | None, after: dict | None) -> list[Draft]:
    """after is the full Studio view of the target after the change, or None to delete it."""
    node = node_of(lane, kind, target_id)
    base = node["_ref"]["version"] if node else 0
    if after is None:
        closing = [Draft(op="close", node_type=kind, node_id=target_id, fields={}, base_version=base)]
        if kind == "workflow":  # a workflow takes its own members with it; shared tools stay
            closing += [Draft(op="close", node_type=m["kind"], node_id=m["id"], fields={}, base_version=m["version"]) for m in items(lane) if m["workflowId"] == target_id]
        return closing + rule_drafts(lane, kind, target_id, None)
    body = {key: value for key, value in (node or {}).items() if key not in ("_ref", STUDIO)}
    studio = {key: value for key, value in after.items() if key != "version"}
    drafts = [Draft(op="update" if node else "add", node_type=kind, node_id=after["id"], fields={**project(kind, after, body), STUDIO: studio}, base_version=base)]
    if kind == "policy" and node:
        drafts += wording_drafts(lane, after, node)
    return drafts + rule_drafts(lane, kind, after["id"], after)


def project(kind: str, after: dict, body: dict) -> dict:
    """The pipeline's fields, rewritten from the Studio view. Workflows have none: they live in Studio only."""
    f = after.get("fields", {})
    if kind == "skill":
        return {**body, "id": after["id"], "name": after["name"], "steps": [step_text(line) for line in f.get("steps", [])],
                "allowed_tools": [tool.removeprefix("tool:") for tool in f.get("tools", [])]}
    if kind == "agent":
        return {**body, "type": "agent", "id": after["id"], "tier": body.get("tier", "L3"), "capabilities": list(f.get("capabilities", []))}
    if kind == "policy" and "window_days" in body:
        return {**body, "window_days": int(f.get("param.days", body["window_days"])),
                "auto_limit": {"amount_minor": int(f.get("param.amountMinor", body["auto_limit"]["amount_minor"])), "currency": str(f.get("param.currency", body["auto_limit"]["currency"]))},
                "escalation": {**body["escalation"], "criticality": int(f.get("criticality", body["escalation"]["criticality"]))}}
    return body


def wording_drafts(lane, after: dict, node: dict) -> list[Draft]:
    """A policy edit closes its old wording in knowledge and writes the new statement, tagged with the new version."""
    key, version, now = after["id"], node["_ref"]["version"] + 1, lane.now.isoformat()
    old = [k for k in lane.graph.latest("knowledge") if (k.get("version_ref") or {}).get("id") == key and not k.get("valid_to")]
    drafts = [Draft(op="update", node_type="knowledge", node_id=k["_ref"]["id"], fields={**{x: y for x, y in k.items() if x != "_ref"}, "valid_to": now}, base_version=k["_ref"]["version"])
              for k in old if k["_ref"]["id"] != f"{key}_statement"]
    statement_id = f"{key}_statement"
    current = node_of(lane, "knowledge", statement_id)
    item = {"item_id": statement_id, "kind": "policy", "text": after["fields"].get("statement", ""), "valid_from": now, "valid_to": None, "recorded_at": now,
            "source": {"document_id": f"doc_{key}", "uri": f"studio://{key}", "span": "0:0"}, "verified_by": after["updatedBy"], "score": 0.9,
            "version_ref": {"id": key, "version": version, "branch": "main", "commit_id": "studio"}, "sensitivity": "internal"}
    return drafts + [Draft(op="update" if current else "add", node_type="knowledge", node_id=statement_id, fields=item, base_version=current["_ref"]["version"] if current else 0)]


def rule_drafts(lane, kind: str, target_id: str, after: dict | None) -> list[Draft]:
    """Routing follows Studio: a rule stops (paused) when its workflow or skill is not active, and runs on the skill's first agent."""
    if kind not in ("skill", "workflow"):
        return []
    flows = {w["id"]: w for w in workflows(lane)}
    skills = {s["id"]: s for s in items(lane) if s["kind"] == "skill"}
    if kind == "workflow":
        flows[target_id] = after or {**flows.get(target_id, {}), "status": "retired"}
    else:
        skills[target_id] = after or {**skills.get(target_id, {"fields": {}}), "status": "retired"}
    drafts = []
    for rule in lane.graph.latest("resolver_rule"):
        skill, flow = skills.get(rule["skill_id"]), flows.get(f"wf_{rule['activity_id']}")
        if (kind == "skill" and rule["skill_id"] != target_id) or (kind == "workflow" and f"wf_{rule['activity_id']}" != target_id):
            continue
        agents = (skill or {}).get("fields", {}).get("agents") or [rule["agent_id"]]
        paused = not skill or skill.get("status") != "active" or not flow or flow.get("status") != "active"
        fields = {**{x: y for x, y in rule.items() if x != "_ref"}, "paused": paused, "agent_id": agents[0],
                  "description": (skill or {}).get("fields", {}).get("trigger") or rule["description"]}
        if fields != {x: y for x, y in rule.items() if x != "_ref"}:
            drafts.append(Draft(op="update", node_type="resolver_rule", node_id=rule["_ref"]["id"], fields=fields, base_version=rule["_ref"]["version"]))
    return drafts
