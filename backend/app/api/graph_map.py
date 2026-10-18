# graph_map.py: the 9c read-only policy screens and the knowledge graph. A policy's versions come from the knowledge
# items that cite it (their version_ref), its rule from the graph's policy node. The map links agents, skills, tools,
# policies, documents and facts. Used by: routes.py, tests/test_api_graph.py. Uses: ui_models_graph.py, graph_views.py.
from pathlib import PurePosixPath

from app.api import ui_models_graph as g
from app.api.graph_views import agents_view, resolver_view, skills_view

# Config
COLUMNS = ["agent", "skill", "tool", "policy", "document", "fact"]  # left to right on the map
COLUMN_GAP, ROW_GAP = 240, 120
OPEN = {"capability": None, "roles": []}
STUDIO_LISTS = {"studio/workflows", "studio/tools", "studio/pending", "studio/revisions"}  # Studio comes in 9d; empty until then


def graph_resource(lane, hq: dict, resource: str, query: dict):
    """The 9c screens. Returns None when the resource is not one of them; raises LookupError for an unknown id."""
    kind, _, item_id = resource.partition("/")
    if resource in STUDIO_LISTS:
        return []
    if kind == "agents":
        shown = agents_view(lane, hq)
        if not item_id:
            return shown
        return next((a for a in shown if a["id"] == item_id), None) or not_found()
    if kind == "skills":
        on_main = query.get("branch", "main") == "main"  # other branches come with S14
        return skills_view(lane, hq, item_id or None) if on_main else []
    if kind == "policies":
        return policies_view(lane, hq, item_id or None)
    if resource == "resolver":
        return resolver_view(lane)
    if resource == "graph":
        return graph_view(lane, hq)
    return None


def not_found():
    raise LookupError("not_found")


# --- Policies

def place_in_document(item: dict) -> tuple[str, int]:
    """Where an item sits in its source, so a policy reads in the document's own order."""
    span = item["source"].get("span") or "0:0"
    return item["source"]["document_id"], int(span.split(":")[0])


def policy_versions(lane, hq: dict, key: str) -> list[g.Policy]:
    """Every version of one policy, oldest first. Only the newest has its rule parameters in the graph."""
    node = next((p for p in lane.graph.latest("policy") if p["_ref"]["id"] == key), None)
    if node is None:
        return []
    items = [item for item in lane.graph.latest("knowledge") if (item.get("version_ref") or {}).get("id") == key]
    versions = sorted({item["version_ref"]["version"] for item in items} | {node["_ref"]["version"]})
    label = hq["graph_labels"]["policies"].get(key, {})
    skills = {s["id"]: s["name"] for s in skills_view(lane, hq)}
    latest_rule = {"kind": "refund", "params": {"windowDays": node["window_days"], "autoLimitMinor": node["auto_limit"]["amount_minor"],
                                                "currency": node["auto_limit"]["currency"], "approverTier": node["escalation"]["approvers"]["tier"]}}
    shown = []
    for i, version in enumerate(versions):
        mine = sorted((item for item in items if item["version_ref"]["version"] == version), key=place_in_document)
        closed = next((item["valid_to"] for item in mine if item["valid_to"]), None)
        shown.append(g.Policy(
            id=f"{key}_v{version}", key=key, tenant_id=lane.seed["tenant_id"], name=label.get("name", key), version=version, branch=node["_ref"]["branch"],
            cluster_id=lane.seed["cluster_id"], statement=" ".join(item["text"] for item in mine), criticality=node["escalation"]["criticality"],
            rule=latest_rule if version == node["_ref"]["version"] else {"kind": "refund", "params": {}},
            valid_from=min((str(item["valid_from"]) for item in mine), default=lane.now.isoformat()), valid_to=str(closed) if closed else None,
            recorded_at=min((str(item["recorded_at"]) for item in mine), default=lane.now.isoformat()),
            superseded_by=f"{key}_v{versions[i + 1]}" if i + 1 < len(versions) else None, evidence=[item["item_id"] for item in mine],
            freshness={"intervalClosed": closed is not None, "driftPointAt": None, "conformance": 1.0, "conflictingEvidence": 0, "outdatedRelianceRate": 0.0},
            dependents=[{"type": "skill", "id": skill_id, "label": skills.get(skill_id, skill_id)} for skill_id in label.get("skills", [])],
            dri=label.get("dri", ""),
        ))
    return shown


def policies_view(lane, hq: dict, key: str | None = None) -> list[dict]:
    keys = [key] if key else [p["_ref"]["id"] for p in lane.graph.latest("policy")]
    return [policy.ui() for k in keys for policy in policy_versions(lane, hq, k)]


# --- Knowledge graph

def graph_view(lane, hq: dict) -> dict:
    """Agents use skills, skills use tools, policies govern skills, documents evidence policies. Facts sit on the right."""
    nodes: list[tuple[str, str, str, str, str]] = []  # (id, type, label, ref, sensitivity)
    edges: list[tuple[str, str, str]] = []
    labels = hq["graph_labels"]
    for agent in lane.graph.latest("agent"):
        nodes.append((f"agent:{agent['_ref']['id']}", "agent", labels["agents"].get(agent["_ref"]["id"], {}).get("name", agent["_ref"]["id"]), agent["_ref"]["id"], "internal"))
    for rule in lane.graph.latest("resolver_rule"):
        edges.append((f"agent:{rule['agent_id']}", f"skill:{rule['skill_id']}", "uses"))
    tools = set()
    for skill in lane.graph.latest("skill"):
        nodes.append((f"skill:{skill['_ref']['id']}", "skill", skill["name"], skill["_ref"]["id"], "internal"))
        for tool in skill["allowed_tools"]:
            tools.add(tool)
            edges.append((f"skill:{skill['_ref']['id']}", f"tool:{tool}", "uses"))
    nodes += [(f"tool:{tool}", "tool", tool.replace("_", " "), tool, "internal") for tool in sorted(tools)]
    for policy in lane.graph.latest("policy"):
        key = policy["_ref"]["id"]
        nodes.append((f"policy:{key}", "policy", labels["policies"].get(key, {}).get("name", key), key, "internal"))
        edges += [(f"policy:{key}", f"skill:{skill_id}", "governs") for skill_id in labels["policies"].get(key, {}).get("skills", [])]
    documents = {}
    for item in lane.graph.latest("knowledge"):
        if item["kind"] == "fact":
            nodes.append((f"fact:{item['item_id']}", "fact", item["text"][:48], item["item_id"], item["sensitivity"]))
            continue
        doc = item["source"]["document_id"]
        documents.setdefault(doc, (PurePosixPath(item["source"]["uri"]).stem.replace("_", " "), item["sensitivity"]))
        if policy_key := (item.get("version_ref") or {}).get("id"):
            edges.append((f"document:{doc}", f"policy:{policy_key}", "evidences"))
    nodes += [(f"document:{doc}", "document", name, doc, sensitivity) for doc, (name, sensitivity) in documents.items()]
    return g.Graph(nodes=placed(nodes, lane.seed["cluster_id"]), edges=[
        g.GraphEdge(id=f"{source}>{target}", source=source, target=target, kind=kind, requires_capability=None)
        for source, target, kind in dict.fromkeys(edges)  # one edge per pair, in first-seen order
    ]).ui()


def placed(nodes: list[tuple[str, str, str, str, str]], cluster_id: str) -> list[g.GraphNode]:
    """A steady layout: one column per node type, rows in order."""
    rows: dict[str, int] = {}
    shown = []
    for node_id, node_type, label, ref, sensitivity in nodes:
        row = rows[node_type] = rows.get(node_type, -1) + 1
        shown.append(g.GraphNode(id=node_id, type=node_type, label=label, ref_id=ref, cluster_id=cluster_id, sensitivity=sensitivity, requires=OPEN,
                                 x=COLUMNS.index(node_type) * COLUMN_GAP, y=row * ROW_GAP))
    return shown
