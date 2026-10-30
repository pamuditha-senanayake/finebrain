# test_memory_outage.py: stage 5e of the living memory, every outage designed. A store down while a trace is kept, Valkey
# down while a trace is claimed, the records store down after triage counted, the shop down while polling, and S3 down at
# night: each ends retried (a dead letter replayed, or the next pass) and never half done, never counted twice, never lost.
# Uses: app/pipeline/stages_memory_flow.py, stages_memory_outside.py, stages_memory_tidy.py, tests/test_chain.py, tests/test_memory_tidy.py.
from datetime import timedelta

import psycopg
import valkey

from app.pipeline import stages_memory_flow as flow
from app.pipeline import stages_memory_outside as outside
from app.pipeline import stages_memory_tidy as night
from tests.test_chain import run_sample
from tests.test_memory_skeleton import NOW, stripe_refund
from tests.test_memory_tidy import lane_of


def fails_once(target, name: str, error: Exception):
    """Make one store method fail on its first call only, as a short outage does."""
    real = getattr(target, name)
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise error
        return real(*args, **kwargs)

    setattr(target, name, flaky)


def replay(lane, topic: str, group: str) -> None:
    """What an operator's replay does: send each dead letter of this group again, with its own event id."""
    for letter in [l for l in lane.bus.dead_letters(topic) if l.consumer_group == group]:
        lane.bus.redeliver(topic, letter.original)
    lane.bus.drain()


def triage_again(lane):
    """Run the run's record through the memory again, as a fresh lane would after a restart."""
    envelope = lane.bus.topics["runs.completed"][-1]
    lane.bus.handled.discard(f"memory_traces:{envelope.event_id}")
    return envelope


def test_the_trace_store_down_while_keeping_a_trace_is_retried_by_replay():
    lane, _ = run_sample("s2")
    envelope = triage_again(lane)
    run_id = envelope.payload["run_id"]
    lane.traces.rows.pop(f"tr-{run_id}")  # as if the trace had never been kept
    lane.records.versions.pop((flow.MATCH_KIND, f"tr-{run_id}"))
    fails_once(lane.traces, "save", psycopg.OperationalError("connection refused"))
    lane.bus.redeliver("runs.completed", envelope)
    lane.bus.drain()
    assert lane.traces.get(f"tr-{run_id}") is None and lane.bus.dead_letters("runs.completed")  # refused, kept as a dead letter
    lane.memory_claims.clear()  # the first triage's claim times out, as a Valkey claim does after a minute
    replay(lane, "runs.completed", "memory_traces")
    assert lane.traces.get(f"tr-{run_id}") is not None and lane.records.load(flow.MATCH_KIND, f"tr-{run_id}")


def test_valkey_down_while_claiming_leaves_nothing_half_done_and_replay_finishes():
    lane, _ = run_sample("s2")
    envelope = lane.bus.topics["traces.recorded"][-1]
    trace_id = envelope.payload["trace_id"]
    lane.records.versions.pop((flow.MATCH_KIND, trace_id))
    lane.records.versions.pop((flow.REVIEW_KIND, trace_id))
    lane.memory_claims = type("Down", (set,), {"claim": lambda self, key: (_ for _ in ()).throw(valkey.ConnectionError("no route"))})()
    lane.bus.handled.discard(f"memory_triage:{envelope.event_id}")
    lane.bus.redeliver("traces.recorded", envelope)
    lane.bus.drain()
    assert lane.records.load(flow.MATCH_KIND, trace_id) is None  # nothing matched while the claim could not be taken
    lane.memory_claims = set()  # Valkey is back
    replay(lane, "traces.recorded", "memory_triage")
    assert lane.records.load(flow.MATCH_KIND, trace_id) and len(lane.records.history(flow.REVIEW_KIND, trace_id)) == 1


def test_the_records_store_down_after_triage_counted_never_counts_twice():
    lane, _ = run_sample("s2")
    envelope = lane.bus.topics["traces.recorded"][-1]
    trace = flow.TraceRecord.model_validate(envelope.payload)
    pattern = flow.memory.confirm(trace, lane.patterns)
    lane.records.versions.pop((flow.MATCH_KIND, trace.trace_id))
    fails_once(lane.records, "save", psycopg.OperationalError("connection refused"))
    lane.memory_claims.clear()  # the first triage's claim has timed out
    lane.bus.handled.discard(f"memory_triage:{envelope.event_id}")
    lane.bus.redeliver("traces.recorded", envelope)
    lane.bus.drain()  # triage counted the trace, then could not keep the match: a dead letter
    lane.memory_claims.clear()  # the claim's timeout passes
    replay(lane, "traces.recorded", "memory_triage")
    assert lane.patterns.area_patterns(trace.area)[pattern.key].count == 1  # counted once, though triage ran twice
    assert lane.records.load(flow.MATCH_KIND, trace.trace_id)["match"] == "normal"


def test_the_shop_down_while_polling_is_counted_and_tried_next_pass():
    lane, _ = run_sample("s2")
    lane.memory_claims.clear()
    original = outside.orders_database
    outside.orders_database = lambda lane: (_ for _ in ()).throw(psycopg.OperationalError("shop unreachable"))
    try:
        outside.last_polled.clear()
        outside.poll_due(lane)  # never raises: the polling loop must outlive the shop
    finally:
        outside.orders_database = original
    assert lane.records.list_kind(outside.CURSOR_KIND) == []


def test_s3_down_at_night_removes_nothing_from_the_warm_tier():
    lane = lane_of(False)
    old = stripe_refund(1).model_copy(update={"started_at": NOW - timedelta(days=40)})
    lane.traces.save(old)
    lane.object_store = type("Down", (dict,), {"__setitem__": lambda self, key, value: (_ for _ in ()).throw(OSError("S3 unreachable"))})()
    try:
        night.tidy(lane, "test")
    except OSError:
        pass  # the Distiller's night fails loudly and runs again tomorrow
    assert lane.traces.get(old.trace_id) == old  # archive first: nothing left the warm tier without its copy in S3
    assert lane.records.load(night.RUN_KIND, NOW.date().isoformat()) is None
