# hq2_records.py: the first half of Finebase HQ-2's stored history: Library documents, one connection per platform, verified facts
# (the vault), the policies that Workflow Studio would hold, and the commits that dated their changes. Every writer checks first, so
# running it twice adds nothing. Used by: seed_hq2.py. Uses: hq2_cast.py, hq2_docs.py, hq2_world.py, the lane's records and graph.
from datetime import datetime

from app.api.studio_model import STUDIO
from app.api.studio_seed import meta
from app.pipeline import filing
from app.pipeline.conn_call import Connection
from app.pipeline.conn_spec import Endpoint, Manifest
from app.pipeline.contracts_graph import Commit
from app.pipeline.stages_file import DocumentRecord
from app.pipeline.stages_version import BranchRecord
from scripts.hq2_cast import CLUSTER, PLATFORMS
from scripts.hq2_docs import DOCS, FACTS, POLICIES
from scripts.hq2_world import ACTIVITY_CLUSTER, FOUNDER, LINKS, SCHEME, knowledge, policy_documents, stamp, uri_of

# Config
SEEDED_BY = "h-pamuditha"
UPLOADER = {"slack": "h-ruwan", "whatsapp": "h-imashi", "gmail": "h-imashi", "meet": "h-ruwan", "notion": "h-tharushi", "github": "h-kavindu", "stripe": "h-tharushi",
            "wise": "h-tharushi", "mercury": "h-tharushi", "blaze": "h-tharushi", "gdocs": "h-imashi", "gdrive": "h-imashi"}
GROUPS = {"slack": "Client conversations", "whatsapp": "Client conversations", "gmail": "Client conversations", "meet": "Client conversations", "notion": "Team work", "github": "Team work",
          "stripe": "Money", "wise": "Money", "mercury": "Money", "blaze": "Money", "gdocs": "Documents", "gdrive": "Documents"}
PURPOSE = {"slack": "client channel messages", "whatsapp": "client chats and videos", "gmail": "client emails", "meet": "meeting transcripts", "notion": "the old task board", "github": "merged work",
           "stripe": "invoices and payments", "wise": "transfers and contractor pay", "mercury": "the US bank account", "blaze": "the monthly cloud bill", "gdocs": "policies, grants and notes", "gdrive": "contracts, decks and lists"}
RECENT = "2026-10-28T17:30:00+05:30"


def all_documents() -> list[tuple]:
    """Every document, policy versions first: (id, platform, title, domain, sensitivity, date, paragraphs)."""
    policies = [(d["id"], d["platform"], d["title"], d["domain"], d["sensitivity"], d["date"], d["paragraphs"]) for d in policy_documents()]
    return policies + DOCS


def seed_documents(lane) -> int:
    """A Library record for each document, pointing at the chunks already in the graph. Returns how many were added."""
    added, chunk_ids = 0, {}
    for node in knowledge():
        chunk_ids.setdefault(node["source"]["document_id"], []).append(node["item_id"])
    for doc_id, platform, title, domain, sens, day, paragraphs in all_documents():
        if lane.records.load("document", doc_id):
            continue
        rule, uri = filing.rule_for(lane.seed, title, title), uri_of(platform, title)
        lane.records.save("document", doc_id, DocumentRecord(
            document_id=doc_id, title=title, filename=uri.rsplit("/", 1)[1], kind=".txt", size_bytes=sum(len(p) for p in paragraphs) + 200, uploaded_by=UPLOADER[platform],
            uploaded_at=datetime.fromisoformat(stamp(day, 10)), sensitivity=sens, status="done", original_uri=uri, chunk_ids=chunk_ids.get(doc_id, []),
            personal_data=platform in ("slack", "whatsapp", "gmail", "meet"), domain=domain, filing_rule=rule["id"], doc_type=rule["type"] or "file",
            retention_days=rule["retention_days"], chain_key=f"{rule['type']}:{title.lower()}", chain_id=doc_id))
        added += 1
    return added


def seed_connections(lane) -> int:
    """One connection per platform, grouped by purpose. All live and tested except the Notion board, which is paused (A11)."""
    counts = {}
    for _, platform, *_ in DOCS:
        counts[platform] = counts.get(platform, 0) + 1
    added = 0
    for pid, name, *_ in PLATFORMS:
        connection_id = f"conn_{pid}"
        if lane.records.load("connection", connection_id):
            continue
        live = pid != "notion"
        lane.records.save("connection", connection_id, Connection(
            connection_id=connection_id, purpose="intake", name=name, system=name, goal=f"Read {PURPOSE[pid]} into the brain, read only.", platform=GROUPS[pid], kind="api",
            status="live" if live else "paused", manifest=Manifest(name=name, purpose="intake", base_url=f"https://{SCHEME[pid]}.example.invalid/api",
                                                                  actions={"read": Endpoint(method="GET", path="/items")}),
            secrets_set=["api_key"], tests=[{"item": "Can read", "ok": True, "detail": "Read 3 sample items"}] if live else [], tested_at=RECENT if live else None,
            created_by=SEEDED_BY, events=counts.get(pid, 0) * 14, last_event_at=RECENT if live else "2026-08-21T10:00:00+05:30"))
        added += 1
    return added


def seed_facts(graph) -> int:
    """Verified facts: the vault, and what readiness reads as proof."""
    added = 0
    for fact_id, predicate, kind, key, statement, raw, normalized, since, doc_id in FACTS:
        if graph.history("fact", fact_id):
            continue
        title = next(d[2] for d in DOCS if d[0] == doc_id)
        platform = next(d[1] for d in DOCS if d[0] == doc_id)
        graph.put("fact", fact_id, 1, "cmt_hq2_facts", {
            "item_id": fact_id, "kind": "fact", "text": statement, "predicate": predicate, "subject": {"entity_type": kind, "entity_ref": f"{kind}:{key}"},
            "value": {"type": "text", "raw": raw, "normalized": normalized}, "valid_from": stamp(since), "valid_to": None, "recorded_at": stamp(since, 12), "verified_by": FOUNDER,
            "status": "verified", "sensitivity": "confidential", "score": 0.95, "source": {"document_id": doc_id, "uri": uri_of(platform, title)},
            "evidence": [{"document_id": doc_id, "page": None, "quote": statement}], "version_ref": None})
        added += 1
    return added


def policy_nodes(seed: dict) -> list[tuple[str, int, dict]]:
    """Studio's view of each policy except the refund policy, which the seed already holds: (id, latest version, body)."""
    first_wf = {r["skill_id"]: f"wf_{r['activity_id']}" for r in seed["resolver_rules"]}
    nodes = []
    for key, name, kind, versions in POLICIES:
        if key == "policy_refund":
            continue
        latest = versions[-1]
        linked = next((s for s, keys in LINKS.items() if key in keys), None)
        fields = {"statement": " ".join(latest[3]), "ruleKind": kind, "criticality": "3" if kind in ("spend", "payments") else "2", "validFrom": latest[1]}
        nodes.append((key, latest[0], {STUDIO: meta(key, "policy", first_wf.get(linked), name, FOUNDER, fields, f"Made for Finebase HQ-2 from {name.lower()}.")}))
    return nodes


def seed_policies(lane) -> int:
    """The other policies as graph nodes, and each skill and workflow written again (a newer version) so they name the policies that govern them."""
    graph, added = lane.graph, 0
    for key, version, body in policy_nodes(lane.seed):
        if not graph.history("policy", key):
            graph.put("policy", key, version, f"cmt_hq2_{key}_{version}", body)
            added += 1
    policies_of = {skill: list(keys) for skill, keys in LINKS.items()}
    for skill in graph.latest("skill"):
        sid, view = skill["_ref"]["id"], skill.get(STUDIO)
        if view is None or all(p in view["fields"].get("policies", []) for p in policies_of.get(sid, [])):
            continue
        fields = {**view["fields"], "policies": list(dict.fromkeys([*view["fields"].get("policies", []), *policies_of.get(sid, [])]))}
        graph.put("skill", sid, skill["_ref"]["version"] + 1, skill["_ref"]["commit_id"], {**{k: v for k, v in skill.items() if k != "_ref"}, STUDIO: {**view, "fields": fields}})
        added += 1
    skill_policies = {f"wf_{r['activity_id']}": policies_of.get(r["skill_id"], []) for r in lane.seed["resolver_rules"]}
    for flow in graph.latest("workflow"):
        wid = flow["_ref"]["id"]
        member = flow[STUDIO]["members"]
        wanted = [p for p in skill_policies.get(wid, []) if p not in member]
        cluster = ACTIVITY_CLUSTER.get(wid.removeprefix("wf_"), flow[STUDIO]["clusterId"])  # each workflow sits in the cluster whose job it is; the brain's own stay put
        if wanted or flow[STUDIO]["clusterId"] != cluster:
            graph.put("workflow", wid, flow["_ref"]["version"] + 1, flow["_ref"]["commit_id"], {STUDIO: {**flow[STUDIO], "members": [*member, *wanted], "clusterId": cluster}})
            added += 1
    return added


def seed_commits(lane) -> int:
    """The main branch and one commit for each dated policy change, so Versions shows what changed and when."""
    if lane.records.load("branch", "main") is None:
        lane.records.save("branch", "main", BranchRecord(name="main", base=None, head=None, status="protected", description="What agents run on", created_by="system", created_at=datetime.fromisoformat(stamp("2026-07-01"))))
    parent, added = None, 0
    changes = sorted(((v[1], key, name, v[0], v[3]) for key, name, _, versions in POLICIES for v in versions), key=lambda c: (c[0], c[1]))
    for day, key, name, version, lines in changes:
        commit_id = f"cmt_hq2_{key}_{version}"
        if lane.records.load("commit", commit_id):
            parent = commit_id
            continue
        lane.records.save("commit", commit_id, Commit(commit_id=commit_id, parent_commit_id=parent, branch="main", author={"kind": "human", "id": FOUNDER},
                                                      message=f"{name}: version {version} from {day}" if version > 1 else f"{name}: first version",
                                                      changes=[{"op": "update" if version > 1 else "add", "node_type": "policy", "node_id": key, "version": version, "fields": {"statement": " ".join(lines)}}],
                                                      criticality=3, created_at=datetime.fromisoformat(stamp(day, 11))))
        parent, added = commit_id, added + 1
    return added
