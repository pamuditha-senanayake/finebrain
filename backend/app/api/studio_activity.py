# studio_activity.py: a workflow is an activity, the thing being asked. After every Studio change this keeps, in the graph,
# what the pipeline reads about it: the activity's owner agent, its one skill, its policies and the connections its
# sensors listen to, on the workflow node; and one routing rule per connection, so every message on that connection goes
# to this activity (S3 reads the owner and skill from the activity, never from the rule). A draft or paused activity keeps
# its rules paused. A policy of the activity whose wording never reached knowledge (saved before that was built) gets it
# on the next change, so its owner reads it. Used by: studio_changes.py (drafts_of), studio_findings.py, studio_chat_context.py. Uses: conn_call.py, stages_version.py.
from app.api import studio_model
from app.pipeline.conn_call import all_connections
from app.pipeline.stages_version import Draft

# Config
STUDIO = "studio"
ACTIVITY_KEYS = ("activity_id", "owner", "skill_id", "policies", "connections")
CHAT_CHANNEL = "chat"  # what S1 calls a message polled or pushed from a connection's feed (conn_inbound.py)
RULE_DEFAULTS = {"kinds": ["customer_message"], "required_entities": [], "keywords": [], "base_criticality": 0, "due_hours": 4, "priority": 3}


# --- What the activity is

def message_sources(lane) -> dict[str, dict]:
    """The tenant's connections a sensor can listen to: those with a feed of messages, by id. Studio's write path only."""
    return {c.connection_id: {"id": c.connection_id, "name": c.name, "status": c.status, "channel": CHAT_CHANNEL}
            for c in all_connections(lane) if c.manifest is not None and c.manifest.inbound is not None}


def activity_fields(flow: dict, items: dict[str, dict], sources: dict[str, dict]) -> dict:
    """Owner, skill, policies and connections, from the workflow's members. The skill's first agent owns it."""
    members = [items[m] for m in flow["members"] if m in items and items[m].get("status") != "retired"]
    skill = next((m for m in members if m["kind"] == "skill"), None)
    agents = [m["id"] for m in members if m["kind"] == "agent"]
    named = [a for a in (skill or {}).get("fields", {}).get("agents", []) if a in agents]
    return {"activity_id": flow["id"].removeprefix("wf_"), "owner": (named or agents or [None])[0], "skill_id": skill["id"] if skill else None,
            "policies": [m["id"] for m in members if m["kind"] == "policy"],
            "connections": [m["fields"].get("source") for m in members if m["kind"] == "sensor" and m["fields"].get("source") in sources]}


def rule_for(flow: dict, fields: dict, source: dict) -> dict:
    """The routing rule that sends every message on one connection to this activity."""
    ready = flow.get("status") == "active" and fields["owner"] and fields["skill_id"]
    return {"rule_id": f"rr_{fields['activity_id']}_{source['id']}", "description": f"Every message on {source['name']} goes to {flow['name']}",
            "activity_id": fields["activity_id"], "channels": [source["channel"]], "connectors": [source["id"]], **RULE_DEFAULTS,
            "skill_id": fields["skill_id"], "agent_id": fields["owner"], "paused": not ready}


# --- Drafts for S14

def latest(lane, kind: str, node_id: str) -> dict | None:
    versions = lane.graph.history(kind, node_id)
    return versions[-1] if versions and not versions[-1].get("_closed") else None


def with_activity(lane, drafts: list[Draft], flow: dict, fields: dict) -> list[Draft]:
    """The workflow node carries the activity's fields: merged into its draft when the change has one, else a new one."""
    mine = next((d for d in drafts if d.node_type == "workflow" and d.node_id == flow["id"] and d.op != "close"), None)
    if mine is not None:
        return [d.model_copy(update={"fields": {**d.fields, **fields}}) if d is mine else d for d in drafts]
    node = latest(lane, "workflow", flow["id"])
    if node is None or all(node.get(key) == fields[key] for key in ACTIVITY_KEYS):
        return drafts
    body = {key: value for key, value in node.items() if key != "_ref"}
    return drafts + [Draft(op="update", node_type="workflow", node_id=flow["id"], fields={**body, **fields}, base_version=node["_ref"]["version"])]


def rule_drafts(lane, flow: dict | None, fields: dict | None, sources: dict[str, dict], activity_id: str) -> list[Draft]:
    """Add or update the rule of each connection the activity listens to; close the ones it stopped listening to."""
    wanted = {rule["rule_id"]: rule for rule in (rule_for(flow, fields, sources[c]) for c in fields["connections"])} if flow else {}
    mine = [r for r in lane.graph.latest("resolver_rule") if r["activity_id"] == activity_id and r.get("connectors")]
    drafts = [Draft(op="close", node_type="resolver_rule", node_id=r["_ref"]["id"], fields={}, base_version=r["_ref"]["version"])
              for r in mine if r["_ref"]["id"] not in wanted]
    for rule_id, rule in wanted.items():
        current = latest(lane, "resolver_rule", rule_id)
        if current is None or {k: v for k, v in current.items() if k != "_ref"} != rule:
            drafts.append(Draft(op="update" if current else "add", node_type="resolver_rule", node_id=rule_id, fields=rule, base_version=current["_ref"]["version"] if current else 0))
    return drafts


def drafts(lane, drafts_so_far: list[Draft], flow_id: str, flow_after: dict | None, items_after: dict[str, dict]) -> list[Draft]:
    """The change's drafts plus what keeps the activity and its routing true. A deleted workflow closes its rules."""
    sources = message_sources(lane)
    activity_id = flow_id.removeprefix("wf_")
    if flow_after is None:
        return drafts_so_far + rule_drafts(lane, None, None, sources, activity_id)
    fields = activity_fields(flow_after, items_after, sources)
    return with_activity(lane, drafts_so_far, flow_after, fields) + rule_drafts(lane, flow_after, fields, sources, activity_id) + missing_wording(lane, drafts_so_far, fields, items_after)


def missing_wording(lane, drafts_so_far: list[Draft], fields: dict, items: dict[str, dict]) -> list[Draft]:
    """The wording of each of the activity's policies that has none in knowledge yet, read by key."""
    written = {d.node_id for d in drafts_so_far if d.node_type == "knowledge"}
    missing = [pid for pid in fields["policies"] if f"{pid}_statement" not in written and latest(lane, "knowledge", f"{pid}_statement") is None
               and (items[pid].get("fields") or {}).get("statement")]
    return [d for pid in missing for d in studio_model.wording_drafts(lane, items[pid], latest(lane, "policy", pid))]
