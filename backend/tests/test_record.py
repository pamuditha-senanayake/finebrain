# test_record.py: S10 step 7 (traces in S3, hash-chained audit log, live stream, personal-data guard) and step 8
# (trace store down, recorder down then replayed, duplicate and tampered audit entries). Postgres cases skip if it is down.
# Uses: stages_record.py, audit.py, ui_stream.py, recorder.py, retry.py, orchestrate.py, tests/golden.py.
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.pipeline import fakes, observe, orchestrate, stages_record
from app.pipeline.audit import PostgresAudit, verify_chain
from app.pipeline.retry import replay_dead_letters
from app.pipeline.store_postgres import connect, database_is_up
from app.pipeline.ui_stream import create_stream_app
from tests.golden import NOW, RAW, SEED, recorded_answers

# Config
S2_RAW, S3_RAW = RAW["s2_refund_monthly_in_policy"], RAW["s3_refund_annual_late_large"]


# --- Helpers

def run_lane(*raws):
    """A memory pipeline after these raw signals have gone all the way through."""
    observe.reset_counts()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    for raw in raws:
        orchestrate.capture_signal(lane, raw)
        lane.bus.drain()
    return lane


class TracesDown(dict):
    """An object store whose trace folder cannot be written; raw bodies still work."""

    def __setitem__(self, uri, body):
        if "/traces/" in uri:
            raise ConnectionError("store down")
        super().__setitem__(uri, body)


# --- Traces

def test_trace_is_written_where_the_run_record_points():
    lane = run_lane(S2_RAW)
    run = lane.bus.topics["runs.completed"][-1].payload
    trace = json.loads(lane.object_store[run["trace_object_uri"]])
    assert (trace["outcome"], trace["action"]["action_type"], trace["verdict"]["route"]) == ("resolved", "issue_refund", "execute")
    assert "item_payment_s2" in trace["bundle_items"]


def test_trace_store_down_still_publishes_the_run():
    observe.reset_counts()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    lane.object_store = TracesDown()
    orchestrate.capture_signal(lane, S2_RAW)
    lane.bus.drain()
    run = lane.bus.topics["runs.completed"][-1].payload
    assert run["outcome"] == "resolved" and run["trace_object_uri"].startswith("pending:") and observe.read_count("s10.trace_failed") == 1


# --- Audit log

def test_audit_chain_covers_the_run_and_holds():
    lane = run_lane(S2_RAW, S3_RAW)
    entries = lane.audit.in_order()
    assert {entry["topic"] for entry in entries} == {"access.decisions", "actions.executed", "runs.completed", "approvals.requested"}
    assert verify_chain(entries) is None


@pytest.mark.parametrize("tamper", ["edit", "delete"])
def test_tampering_breaks_the_chain_at_that_entry(tamper):
    entries = run_lane(S2_RAW).audit.in_order()
    if tamper == "edit":
        entries[2] = {**entries[2], "body": {**entries[2]["body"], "status": "edited later"}}
    else:
        del entries[2]
    first_bad = 3 if tamper == "edit" else 4  # an edit breaks its own entry; a deletion breaks the one after the gap
    assert verify_chain(entries) == first_bad


def test_same_event_is_audited_once():
    lane = run_lane()
    assert [lane.audit.append("evt_1", "runs.completed", {"a": 1}) for _ in range(2)] == [True, False]


@pytest.mark.skipif(not database_is_up(), reason="no Postgres on localhost:5433")
def test_postgres_audit_detects_an_edit_made_in_the_database():
    connection, tenant = connect(), f"test_{uuid.uuid4().hex[:8]}"
    audit = PostgresAudit(connection, tenant)
    results = [audit.append(f"evt_{number}", "runs.completed", {"run": number}) for number in (1, 2, 3, 3)]
    assert results == [True, True, True, False] and verify_chain(audit.in_order()) is None
    connection.execute("UPDATE audit_log SET body = '{\"run\": 99}' WHERE tenant_id = %s AND seq = 2", (tenant,))
    assert verify_chain(audit.in_order()) == 2


# --- Personal-data guard

def test_leaks_are_masked_before_people_see_them():
    observe.reset_counts()
    shown = stages_record.guard_display({"title": "Call +94 77 123 4567 or nimal.perera@example.lk", "count": 2})
    assert shown == {"title": "Call [masked] or [masked]", "count": 2} and observe.read_count("s10.pii_masked") == 2


# --- Live stream

def test_console_stream_gets_the_runs_events():
    lane = run_lane(S2_RAW)
    body = TestClient(create_stream_app(lane.broadcaster)).get(f"/api/stream?tenant_id={SEED['tenant_id']}&limit=1").text
    assert body.startswith("event: run.updated") and '"status": "resolved"' in body


def test_stream_says_delayed_when_the_recorder_is_behind():
    lane = run_lane(S2_RAW)
    observe.set_flag("recorder_delayed", True)
    body = TestClient(create_stream_app(lane.broadcaster)).get(f"/api/stream?tenant_id={SEED['tenant_id']}&limit=1").text
    observe.reset_counts()  # flags are process-wide; leave none behind
    assert body.startswith("event: delayed")


def test_tenants_only_see_their_own_events():
    lane = run_lane(S2_RAW)
    recent, _ = lane.broadcaster.listen("another_tenant")
    assert recent == []


# --- Recorder down, then replayed

def test_recorder_down_keeps_the_event_for_replay():
    observe.reset_counts()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    real_save = lane.records.save

    def down(*args, **kwargs):
        raise ConnectionError("database down")

    lane.records.save = down
    orchestrate.capture_signal(lane, S2_RAW)
    lane.bus.drain()
    letters = lane.bus.dead_letters("runs.completed")
    assert [(letter.error_code, letter.retryable) for letter in letters] == [("RecorderUnavailable", True)] and observe.read_flag("recorder_delayed")

    lane.records.save = real_save  # the database is back
    replay_dead_letters(lane.bus, "runs.completed")
    lane.bus.drain()
    assert lane.records.list_kind("run")[0]["outcome"] == "resolved" and not observe.read_flag("recorder_delayed")
