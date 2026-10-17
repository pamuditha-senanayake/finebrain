# adapters.py: one place that builds what a pipeline runs on: bus, object store, vault, key sets, records.
# Used by: orchestrate.py, tests/test_e2e.py. Uses: bus_*.py, store_*.py.
# Each real part can be switched on alone, so connectors are plugged in one at a time (step 6).
from app.pipeline import store_postgres, store_s3, store_valkey
from app.pipeline.bus_kafka import KafkaBus, broker_is_up
from app.pipeline.bus_memory import MemoryBus
from app.pipeline.store_memory import MemoryRecords

# Config
ALL_REAL_PARTS = frozenset({"s3", "postgres", "valkey", "kafka"})
UP_CHECKS = {
    "s3": store_s3.s3_is_up,
    "postgres": store_postgres.database_is_up,
    "valkey": store_valkey.valkey_is_up,
    "kafka": broker_is_up,
}


def bus_base(seed: dict) -> dict:
    """Envelope fields that are the same on every message of this pipeline."""
    return {"tenant_id": seed["tenant_id"], "cluster_id": seed["cluster_id"], "env": seed["env"], "branch": "main"}


def make_memory_adapters(seed: dict, now, new_id) -> dict:
    """Everything in memory: fast, no Docker needed."""
    return {
        "bus": MemoryBus(bus_base(seed), now, new_id),
        "object_store": {},
        "vault": {},
        "seen_keys": set(),
        "records": MemoryRecords(seed["tenant_id"]),
    }


def missing_infra(parts: frozenset[str]) -> list[str]:
    """Which of these real parts do not answer right now."""
    return sorted(part for part in parts if not UP_CHECKS[part]())


def real_adapters(parts: frozenset[str] = ALL_REAL_PARTS, topic_prefix: str = ""):
    """Return a builder like make_memory_adapters, with the chosen parts on real infra."""

    def make_adapters(seed: dict, now, new_id) -> dict:
        # Step 1: start from memory, so parts not chosen stay in memory
        adapters = make_memory_adapters(seed, now, new_id)
        tenant = seed["tenant_id"]

        # Step 2: swap in each chosen part
        if "s3" in parts:
            adapters["object_store"] = store_s3.S3ObjectStore(store_s3.connect(), prefix=f"{tenant}/")
        if "postgres" in parts:
            connection = store_postgres.connect()
            adapters["vault"] = store_postgres.PostgresVault(connection, tenant)
            adapters["records"] = store_postgres.PostgresRecords(connection, tenant)
        handled = None
        if "valkey" in parts:
            keys = store_valkey.connect()
            adapters["seen_keys"] = store_valkey.ValkeyKeySet(keys, f"{tenant}:s2_dedup")
            handled = store_valkey.ValkeyKeySet(keys, f"{tenant}:handled")
        bus_class = KafkaBus if "kafka" in parts else MemoryBus
        options = {"topic_prefix": topic_prefix} if "kafka" in parts else {}
        adapters["bus"] = bus_class(bus_base(seed), now, new_id, handled=handled, **options)
        return adapters

    return make_adapters
