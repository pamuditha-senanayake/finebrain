# repair_studio_views.py: gives skills, agents and the policy stored before step 9d their Workflow Studio view. load_seed
# never rewrites a stored node, so a node written before studio_seed.py existed has no "studio" view and Studio answers
# "not found" for it. Each such node gets a new version through S14 with the seed's view added; no row is edited in
# place. A node that moved on from the seed is left alone and reported. Safe to run twice.
# Run from backend/ with Docker up, after a pg_dump:  uv run --env-file .env python -m scripts.repair_studio_views
# Uses: hq.py (seed), adapters.py, bus_memory.py, stages_version.py, store_postgres.py, store_graph.py. Tests import repair.
from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.hq import load_hq, unique_id
from app.api.studio_model import STUDIO
from app.pipeline import stages_version, store_postgres
from app.pipeline.adapters import bus_base
from app.pipeline.bus_memory import MemoryBus
from app.pipeline.contracts_graph import CommitAuthor
from app.pipeline.stages_version import Draft
from app.pipeline.store_graph import PostgresGraph

# Config
AUTHOR = CommitAuthor(kind="studio", id="system")
MESSAGE = "Add the Workflow Studio view to nodes stored before Studio existed"
CRITICALITY = 1  # Studio metadata only: nothing the pipeline reads changes


# --- Helpers

def seeded_nodes(seed: dict) -> list[tuple[str, str, dict]]:
    """Every seed node that carries a Studio view: (kind, id, body)."""
    policy = seed["refund_policy"]
    nodes = [("skill", s["id"], s) for s in seed["skills"]] + [("agent", key, a) for key, a in seed["agents"].items()]
    return [n for n in nodes + [("policy", policy["policy_ref"]["id"], policy)] if STUDIO in n[2]]


def stored_node(graph, kind: str, node_id: str) -> dict | None:
    return next((node for node in graph.latest(kind) if node["_ref"]["id"] == node_id), None)


def plan(graph, seed: dict) -> tuple[list[Draft], list[str]]:
    """Drafts for the nodes missing their view, and the ids skipped because they no longer match the seed."""
    drafts, skipped = [], []
    for kind, node_id, body in seeded_nodes(seed):
        node = stored_node(graph, kind, node_id)
        if node is None or STUDIO in node:
            continue
        stored = {key: value for key, value in node.items() if key != "_ref"}
        if stored != {key: value for key, value in body.items() if key != STUDIO}:
            skipped.append(node_id)  # someone changed it since the seed; the seed's view would describe the wrong node
            continue
        drafts.append(Draft(op="update", node_type=kind, node_id=node_id, fields={**stored, STUDIO: body[STUDIO]}, base_version=node["_ref"]["version"]))
    return drafts, skipped


# --- The repair

def repair(lane, seed: dict) -> dict:
    """One S14 commit for every node that lacks its view. Returns what was repaired and what was skipped."""
    drafts, skipped = plan(lane.graph, seed)
    if not drafts:
        return {"commit": None, "repaired": [], "skipped": skipped}
    commit = stages_version.apply(lane, AUTHOR, MESSAGE, drafts, CRITICALITY)
    return {"commit": commit.commit_id, "repaired": [f"{c.node_id} v{c.version}" for c in commit.changes], "skipped": skipped}


def postgres_lane(seed: dict):
    """Just what S14 needs on real Postgres. The release goes to an in-memory bus: its one reader re-embeds knowledge,
    and this repair changes none."""
    now, connection = datetime.now(timezone.utc), store_postgres.connect()
    return SimpleNamespace(graph=PostgresGraph(connection, seed["tenant_id"]), records=store_postgres.PostgresRecords(connection, seed["tenant_id"]),
                           bus=MemoryBus(bus_base(seed), now, unique_id), new_id=unique_id, now=now)


if __name__ == "__main__":
    hq_seed, _ = load_hq()
    print(repair(postgres_lane(hq_seed), hq_seed))
