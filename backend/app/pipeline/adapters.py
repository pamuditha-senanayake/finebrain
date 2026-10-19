# adapters.py: one place that builds what a pipeline runs on: bus, object store, vault, key sets, records, graph.
# Used by: orchestrate.py, tests/test_e2e.py. Uses: bus_*.py, store_*.py, temporal_*.py.
# Each real part can be switched on alone, so connectors are plugged in one at a time (step 6).
import os
import time

from app.pipeline import access, embeddings, store_postgres, store_s3, store_valkey
from app.pipeline.audit import MemoryAudit, PostgresAudit
from app.pipeline.fakes import fake_embed, fake_rerank, make_fake_sender
from app.pipeline.bus_kafka import KafkaBus
from app.pipeline.kafka_admin import broker_is_up
from app.pipeline.bus_memory import MemoryBus
from app.pipeline.store_chunks import MemoryChunks, PostgresChunks, load_chunks
from app.pipeline.store_entities import MemoryEntities, PostgresEntities
from app.pipeline.store_graph import MemoryGraph, PostgresGraph, load_seed
from app.pipeline.store_memory import MemoryRecords
from app.pipeline.tool_runners import MemoryRateLimiter, MemoryResults, ValkeyRateLimiter, ValkeyResults
from app.pipeline.ui_stream import Broadcaster
from app.pipeline.temporal_flow import temporal_is_up
from app.pipeline.temporal_runner import TemporalRunner

# Config
ALL_REAL_PARTS = frozenset({"s3", "postgres", "valkey", "kafka", "temporal", "opa"})  # "voyage" is opt-in: it costs money
UP_CHECKS = {
    "s3": store_s3.s3_is_up,
    "postgres": store_postgres.database_is_up,
    "valkey": store_valkey.valkey_is_up,
    "kafka": broker_is_up,
    "temporal": temporal_is_up,
    "voyage": lambda: "VOYAGE_API_KEY" in os.environ,
    "opa": access.opa_is_up,
}


def bus_base(seed: dict) -> dict:
    """Envelope fields that are the same on every message of this pipeline."""
    return {"tenant_id": seed["tenant_id"], "cluster_id": seed["cluster_id"], "env": seed["env"], "branch": "main"}


def make_memory_adapters(seed: dict, now, new_id) -> dict:
    """Everything in memory: fast, no Docker needed."""
    adapters = {
        "bus": MemoryBus(bus_base(seed), now, new_id),
        "object_store": {},
        "vault": {},
        "seen_keys": set(),
        "records": MemoryRecords(seed["tenant_id"]),
        "graph": seeded(MemoryGraph(seed["tenant_id"]), seed),
        "embed": fake_embed,  # tests never pay for API calls; the "voyage" part switches to the real service
        "rerank": fake_rerank,
        "chunks": MemoryChunks(),
        "check_access": access.make_memory_checker(seed["people"]),
        "tooling": {"limiter": MemoryRateLimiter(), "results": MemoryResults(), "sleep": time.sleep,
                    "send_email": make_fake_sender()[0]},  # real Gmail sending comes with connector OAuth
        "audit": MemoryAudit(),
        "broadcaster": Broadcaster(),
        "entities": MemoryEntities(),
    }
    load_chunks(adapters["chunks"], adapters["graph"], adapters["embed"])
    return adapters


def seeded(graph, seed: dict):
    """A graph with the seed loaded, until S14 and Workflow Studio write to it."""
    load_seed(graph, seed)
    return graph


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
            adapters["graph"] = seeded(PostgresGraph(connection, tenant), seed)
            adapters["chunks"] = PostgresChunks(connection, tenant)
            adapters["audit"] = PostgresAudit(connection, tenant)
            adapters["entities"] = PostgresEntities(connection, tenant)
        handled = None
        if "valkey" in parts:
            keys = store_valkey.connect()
            adapters["seen_keys"] = store_valkey.ValkeyKeySet(keys, f"{tenant}:s2_dedup")
            handled = store_valkey.ValkeyKeySet(keys, f"{tenant}:handled")
            adapters["tooling"].update(limiter=ValkeyRateLimiter(keys), results=ValkeyResults(keys, f"{tenant}:results"))
        bus_class = KafkaBus if "kafka" in parts else MemoryBus
        options = {"topic_prefix": topic_prefix} if "kafka" in parts else {}
        adapters["bus"] = bus_class(bus_base(seed), now, new_id, handled=handled, **options)
        if "opa" in parts:
            adapters["check_access"] = access.make_opa_checker(seed["people"])
        if "voyage" in parts:
            adapters["embed"], adapters["rerank"] = embeddings.voyage_embed, embeddings.voyage_rerank
        load_chunks(adapters["chunks"], adapters["graph"], adapters["embed"])
        if "temporal" in parts:
            adapters["runner"] = TemporalRunner()  # build_lane starts it once the lane exists
        return adapters

    return make_adapters
