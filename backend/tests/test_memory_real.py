# test_memory_real.py: stage 5b of the living memory on real infra. Anna's refund runs on SeaweedFS, Postgres, Valkey,
# Redpanda and OPA; the memory follows it: the trace is kept in Postgres with its access decisions, K16 and K17 are read
# back from Redpanda, and the surprise waits in To review. Then two workers triage the same trace at once and give one
# result, and two people pressing Keep on one surprise at once keep it once. Skips when services are down. Uses: stages_memory_flow.py, adapters.py, tests/test_s7_s10_real.py, tests/s7_world.py.
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.pipeline import stages_memory_flow as flow
from app.pipeline import store_postgres, store_valkey
from app.pipeline.adapters import MEMORY_CLAIM_SECONDS, missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from app.pipeline.store_drift import PostgresDrift
from app.pipeline.store_patterns import PostgresPatterns
from tests.s6_world import ask, refund, scripted
from tests.s7_world import full_lane, says
from tests.test_s1_real import read_topic
from tests.test_s1_refund_chat import FIRST, SECOND
from tests.test_s5_real import S5_PARTS, parts
from tests.test_s7_s10_real import seed_for

# Config
NEEDS_INFRA = pytest.mark.skipif(bool(missing_infra(S5_PARTS)), reason="infra not answering")


class Published:
    """A worker's own outbox, so two threads never share one Kafka producer in the test."""

    def __init__(self):
        self.sent: list[tuple[str, object]] = []

    def publish(self, topic, event_type, payload, producer, cause=None):
        self.sent.append((topic, payload))


def worker(lane) -> SimpleNamespace:
    """A second worker of the same tenant: its own connections, the same Postgres tables and Valkey claims."""
    tenant = lane.seed["tenant_id"]
    connection = store_postgres.connect()
    return SimpleNamespace(seed=lane.seed, now=lane.now, bus=Published(), records=store_postgres.PostgresRecords(connection, tenant), patterns=PostgresPatterns(connection, tenant),
                           drift=PostgresDrift(connection, tenant),
                           memory_claims=store_valkey.ValkeyKeySet(store_valkey.connect(), f"{tenant}:memory_claims", MEMORY_CLAIM_SECONDS))


def triage_or_held(lane, envelope) -> str:
    try:
        flow.on_trace(lane, envelope)
    except flow.TraceClaimed:
        return "held"
    return "sent" if lane.bus.sent else "done"


@NEEDS_INFRA
def test_annas_refund_leaves_a_trace_and_a_surprise_on_real_infra():
    tag = uuid.uuid4().hex[:8]
    lane = full_lane(real_adapters(parts(), topic_prefix=f"mem{tag}."), seed=seed_for(tag))
    try:
        lane.model, _ = scripted(ask(), refund())
        says(lane, FIRST)
        says(lane, SECOND)
        run_id = lane.bus.topics["runs.completed"][-1].payload["run_id"]
        # Step 1: the trace is in Postgres, start to end, with the access decisions it made
        trace = lane.traces.get(f"tr-{run_id}")
        assert trace and trace.outcome == "resolved" and trace.access and type(lane.traces).__name__ == "PostgresTraces"
        # Step 2: K16 and K17 went out on Redpanda, and the surprise waits in To review
        recorded = [m["payload"]["trace_id"] for m in read_topic(f"mem{tag}.traces.recorded", 2)]
        matched = [m["payload"] for m in read_topic(f"mem{tag}.traces.matched", 2)]
        assert f"tr-{run_id}" in recorded and any(m["trace_id"] == f"tr-{run_id}" and m["match"] == "surprise" for m in matched)
        assert lane.records.load(flow.REVIEW_KIND, f"tr-{run_id}")
    finally:
        delete_prefixed_topics(f"mem{tag}.")


@NEEDS_INFRA
def test_two_workers_triaging_one_trace_at_once_give_one_result():
    tag = uuid.uuid4().hex[:8]
    lane = full_lane(real_adapters(parts(), topic_prefix=f"mem{tag}."), seed=seed_for(tag))
    try:
        lane.model, _ = scripted(ask(), refund())
        says(lane, FIRST)
        says(lane, SECOND)
        envelope = lane.bus.topics["traces.recorded"][-1]
        trace_id = envelope.payload["trace_id"]
        # Step 1: forget the first triage, as if it had never run, and free its claim
        lane.records.purge(flow.MATCH_KIND, trace_id)
        lane.records.purge(flow.REVIEW_KIND, trace_id)
        lane.memory_claims.discard(f"triage:{trace_id}")
        # Step 2: two workers take the same trace at the same moment
        workers = [worker(lane), worker(lane)]
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda w: triage_or_held(w, envelope), workers))
        assert results.count("sent") == 1 and set(results) <= {"sent", "held", "done"}
        assert len(lane.records.history(flow.MATCH_KIND, trace_id)) == 1 and len(lane.records.history(flow.REVIEW_KIND, trace_id)) == 1
    finally:
        delete_prefixed_topics(f"mem{tag}.")


@NEEDS_INFRA
def test_security_drift_is_kept_in_postgres_and_goes_out_on_redpanda():
    from app.pipeline.contracts_memory import TraceAccess, TraceRecord

    tag = uuid.uuid4().hex[:8]
    lane = full_lane(real_adapters(parts(), topic_prefix=f"mem{tag}."), seed=seed_for(tag))
    try:
        lane.model, _ = scripted(ask(), refund())
        says(lane, FIRST)
        says(lane, SECOND)
        trace = TraceRecord.model_validate(lane.bus.topics["traces.recorded"][-1].payload)
        deny = TraceAccess(decision_id="d-deny", action="refund:issue", principal_id="agent_x", on_behalf_of=None, decision="deny", effective_tier="internal")
        bad = trace.model_copy(update={"trace_id": "tr-bad", "run_id": "run_bad", "access": [*trace.access, deny]})
        lane.traces.save(bad)
        lane.bus.publish("traces.recorded", "trace.recorded", bad, "test")
        lane.bus.drain()
        held = lane.drift.open_flag("security", "agent_x")
        assert type(lane.drift).__name__ == "PostgresDrift" and held and held.evidence_trace_ids == ["tr-bad"]
        assert any(m["payload"]["flag_id"] == held.flag_id for m in read_topic(f"mem{tag}.drift.flags", 1))
    finally:
        delete_prefixed_topics(f"mem{tag}.")


def pressing_keep(lane, trace_id: str) -> str:
    from app.api import memory_fixes

    try:
        memory_fixes.confirm_surprise(lane, trace_id, "h-founder")
    except memory_fixes.NotPossible as reason:
        return str(reason)
    return "kept"


@NEEDS_INFRA
def test_two_people_keeping_one_surprise_at_once_keep_it_once():
    from app.pipeline.audit import PostgresAudit
    from app.pipeline.store_traces import PostgresTraces

    tag = uuid.uuid4().hex[:8]
    lane = full_lane(real_adapters(parts(), topic_prefix=f"mem{tag}."), seed=seed_for(tag))
    try:
        lane.model, _ = scripted(ask(), refund())
        says(lane, FIRST)
        says(lane, SECOND)
        trace_id = f"tr-{lane.bus.topics['runs.completed'][-1].payload['run_id']}"
        # Step 1: two workers, each with its own connection, as two API processes would be
        workers = [worker(lane), worker(lane)]
        for each in workers:
            connection = store_postgres.connect()
            each.traces, each.audit = PostgresTraces(connection, lane.seed["tenant_id"]), PostgresAudit(connection, lane.seed["tenant_id"])
        # Step 2: both press Keep at the same moment; one keeps it, the other hears it is already answered
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda w: pressing_keep(w, trace_id), workers))
        assert sorted(results) == ["already_answered", "kept"]
        pattern_id = lane.records.load(flow.MATCH_KIND, trace_id)["pattern_id"]
        assert sum(lane.patterns.weeks(pattern_id).values()) == 1  # counted once, not once per press
    finally:
        delete_prefixed_topics(f"mem{tag}.")
