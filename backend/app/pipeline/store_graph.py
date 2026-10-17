# store_graph.py: the minimal graph (S14 later owns writes): append-only node versions per branch.
# Holds resolver rules, skills, agents, policies and knowledge. Used by: adapters.py, stages_route.py, tests.
# Uses: nothing local. A version, once written, never changes; a newer version supersedes it.
import psycopg
from psycopg.types.json import Jsonb

# Config
SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    tenant_id   text        NOT NULL,
    branch      text        NOT NULL,
    node_type   text        NOT NULL,
    node_id     text        NOT NULL,
    version     int         NOT NULL,
    commit_id   text        NOT NULL,
    body        jsonb       NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, branch, node_type, node_id, version)
);
"""
SEED_COMMIT = "cmt_seed"


def with_ref(body: dict, node_id: str, version: int, branch: str, commit_id: str) -> dict:
    """A node's body plus its VersionRef, so callers can pin exactly what they read."""
    return {**body, "_ref": {"id": node_id, "version": version, "branch": branch, "commit_id": commit_id}}


class MemoryGraph:
    """The in-memory twin of PostgresGraph."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.nodes: dict[tuple[str, str, str], dict[int, dict]] = {}  # (branch, type, id) -> version -> node

    def put(self, node_type: str, node_id: str, version: int, commit_id: str, body: dict, branch: str = "main") -> None:
        """Write a version once. Writing the same version again changes nothing."""
        versions = self.nodes.setdefault((branch, node_type, node_id), {})
        versions.setdefault(version, with_ref(body, node_id, version, branch, commit_id))

    def latest(self, node_type: str, branch: str = "main") -> list[dict]:
        """The newest version of every node of one type, ordered by id."""
        found = [(key[2], versions) for key, versions in sorted(self.nodes.items()) if key[:2] == (branch, node_type)]
        return [versions[max(versions)] for _, versions in found]


class PostgresGraph:
    """Graph nodes in Postgres, one row per version."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)

    def put(self, node_type: str, node_id: str, version: int, commit_id: str, body: dict, branch: str = "main") -> None:
        """Write a version once. Writing the same version again changes nothing."""
        self.connection.execute(
            """INSERT INTO graph_nodes (tenant_id, branch, node_type, node_id, version, commit_id, body)
               VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (self.tenant_id, branch, node_type, node_id, version, commit_id, Jsonb(body)),
        )

    def latest(self, node_type: str, branch: str = "main") -> list[dict]:
        """The newest version of every node of one type, ordered by id."""
        rows = self.connection.execute(
            """SELECT DISTINCT ON (node_id) node_id, version, commit_id, body FROM graph_nodes
               WHERE tenant_id = %s AND branch = %s AND node_type = %s ORDER BY node_id, version DESC""",
            (self.tenant_id, branch, node_type),
        )
        return [with_ref(body, node_id, version, branch, commit_id) for node_id, version, commit_id, body in rows]


def load_seed(graph, seed: dict) -> None:
    """Put the seed's rules, skills, agents, policy and knowledge into the graph. Safe to run twice."""
    for rule in seed["resolver_rules"]:
        graph.put("resolver_rule", rule["rule_id"], 1, SEED_COMMIT, rule)
    for skill in seed["skills"]:
        graph.put("skill", skill["id"], skill["version"], skill["commit_id"], skill)
    for agent_id, agent in seed["agents"].items():
        graph.put("agent", agent_id, 1, SEED_COMMIT, agent)
    policy = seed["refund_policy"]
    graph.put("policy", policy["policy_ref"]["id"], policy["policy_ref"]["version"], policy["policy_ref"]["commit_id"], policy)
    for item in seed["knowledge"]:
        graph.put("knowledge", item["item_id"], 1, SEED_COMMIT, item)
