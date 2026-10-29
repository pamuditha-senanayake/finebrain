# seed_hq2.py: fills Finebase HQ-2 (tenant finebase-hq-2) with its demo history on the same Postgres, Valkey-free path HQ uses: the
# seed knowledge and policies, documents, connections, facts, runs, approvals, audit entries, chats and Ask history. Safe to run twice:
# every writer checks first. It touches only rows of the tenant finebase-hq-2. Run: uv run python -m scripts.seed_hq2   (Postgres and S3 up)
# Add --reset to clear HQ-2's rows first. Used by: tests/test_hq2_seed.py. Uses: hq2_world.py, hq2_records.py, hq2_history.py, app/api/hq.py, app/pipeline/adapters.py.
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("HQ_TENANT_FILE", "hq2_tenant.json")

from app.api import hq  # noqa: E402  (after the environment names HQ-2's file)
from app.pipeline import store_postgres  # noqa: E402
from app.pipeline.adapters import make_memory_adapters, real_adapters  # noqa: E402
from scripts import hq2_history, hq2_records  # noqa: E402
from scripts.hq2_cast import TENANT_ID  # noqa: E402


def open_lane(parts: frozenset[str]) -> SimpleNamespace:
    """Just enough of a lane to write records: the seed loaded into the graph and the chosen real parts. No bus consumers start."""
    seed, tenant = hq.load_hq()
    build = real_adapters(parts) if parts else make_memory_adapters
    return SimpleNamespace(seed=seed, hq=tenant, now=hq2_history.NOW, signals={}, new_id=lambda prefix: f"{prefix}_hq2", **build(seed, hq2_history.NOW, lambda prefix: f"{prefix}_hq2"))


def reset_tenant(connection, tenant_id: str = TENANT_ID) -> dict:
    """Delete every row of Finebase HQ-2 (and only of it) from each table that has a tenant_id column. For a clean re-seed."""
    if tenant_id != TENANT_ID:
        raise ValueError("reset_tenant only clears Finebase HQ-2")
    tables = [row[0] for row in connection.execute("SELECT table_name FROM information_schema.columns WHERE column_name = 'tenant_id' AND table_schema = 'public'")]
    return {table: connection.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,)).rowcount for table in tables}


def seed_all(lane) -> dict:
    """Every writer once. The counts say how much each added; a second run adds zero."""
    return {"documents": hq2_records.seed_documents(lane), "connections": hq2_records.seed_connections(lane), "facts": hq2_records.seed_facts(lane.graph),
            "policies": hq2_records.seed_policies(lane), "commits": hq2_records.seed_commits(lane), "runs": hq2_history.seed_runs(lane),
            "chats": hq2_history.seed_chats(lane), "asks": hq2_history.seed_asks(lane)}


def main() -> None:
    parts = hq.choose_parts() - {"voyage", "kafka", "temporal", "opa", "valkey"}  # records, graph, chunks, audit and traces only
    if "--reset" in sys.argv:
        print("cleared", {k: v for k, v in reset_tenant(store_postgres.connect()).items() if v})
    lane = open_lane(parts)
    print(f"tenant {lane.seed['tenant_id']} on {sorted(parts) or 'memory'}")
    for name, added in seed_all(lane).items():
        print(f"  {name:12} +{added}")


if __name__ == "__main__":
    sys.exit(main())
