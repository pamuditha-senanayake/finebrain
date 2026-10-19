# test_ready_time.py: step 16 slice 4, readiness over time. An open request escalates once per step (21, 14, 7, 2 days before the
# due day) and the DRI hears of it, the leaders too from step 3; past the due day it expires. The hourly tick runs on a real Temporal
# schedule when Temporal answers. Uses: readiness_time.py, stages_ready.py, api/ready_notices.py, temporal_ready.py, tests/test_ready_gaps.py.
import time
import uuid
from datetime import datetime, timezone

import pytest

from app.api import ready_notices
from app.pipeline import fakes, orchestrate, stages_ready, temporal_ready
from app.pipeline.adapters import missing_infra, real_adapters
from tests.golden import NOW
from tests.test_documents import FOUNDER, SEED, build
from tests.test_ready_gaps import STEWARD, check_now, get

# Config
VAT = "er_ob_vat_2026_09_input_invoices"  # VAT for September falls due on 20 October; the test clock starts on 10 October


# --- Helpers

def on(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


def notices(lane, title: str) -> list[str]:
    return [n["to"] for n in lane.records.list_kind("notification") if n["title"].startswith(title)]


def vat_request(client) -> dict:
    return next(r for r in get(client, "evidence-requests") if r["id"] == VAT)


# --- Escalation

def test_a_request_starts_on_its_step_and_escalates_once_per_step():
    client, lane = build()
    assert vat_request(client)["escalationLevel"] == 2  # nine days out: past the 21 and 14 day steps, no notice for those
    assert notices(lane, "Still needed") == []
    lane.now = on("2026-10-14T08:00:00")  # five days out: step 3 (APIT, due the next day, reaches step 4)
    assert check_now(client).json()["escalated"] == 3  # both VAT items and APIT
    check_now(client)
    assert vat_request(client)["escalationLevel"] == 3 and len(notices(lane, "Still needed: Input VAT")) == 1  # once per step; a DRI who leads hears it once
    assert sum(e["topic"] == "evidence.escalated" for e in lane.audit.in_order()) == 3


def test_from_step_three_the_leaders_hear_too(monkeypatch):
    client, lane = build()
    monkeypatch.setitem(lane.seed["readiness"]["obligations"][0], "dri", STEWARD)  # VAT is the steward's for this test
    get(client, "gaps")
    lane.now = on("2026-10-14T08:00:00")
    check_now(client)
    assert sorted(set(notices(lane, "Still needed: Input VAT"))) == sorted([STEWARD, FOUNDER])


# --- Expiry

def test_past_the_due_day_an_open_request_expires_and_the_next_month_is_asked_for():
    client, lane = build()
    get(client, "gaps")
    lane.now = on("2026-10-21T08:00:00")
    answer = check_now(client).json()
    assert answer["expired"] >= 2 and vat_request(client)["status"] == "expired" and vat_request(client)["escalationLevel"] == 0
    assert notices(lane, "Missed: Input VAT") == [FOUNDER]
    assert "er_ob_vat_2026_10_input_invoices" in {r["id"] for r in get(client, "evidence-requests")}  # October's VAT is now the one due


def test_an_older_request_learns_its_due_day_and_a_too_early_expiry_is_undone():
    client, lane = build()
    get(client, "gaps")
    stored = lane.records.load("evidence_request", VAT)
    lane.records.save("evidence_request", VAT, stages_ready.EvidenceRequest.model_validate({**stored, "obligation_due_at": None, "status": "expired"}))
    check_now(client)
    assert vat_request(client)["status"] == "open" and lane.records.load("evidence_request", VAT)["obligation_due_at"].startswith("2026-10-20")


# --- The hourly schedule on real Temporal

@pytest.mark.skipif(bool(missing_infra(frozenset({"temporal"}))), reason="no Temporal on localhost:7233")
def test_the_hourly_schedule_runs_the_check_on_temporal():
    seed = {**SEED, "tenant_id": f"test_ready_{uuid.uuid4().hex[:8]}"}
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, real_adapters(frozenset({"temporal"})))
    ran = []
    try:
        schedule_id = temporal_ready.start(lane.runner, seed["tenant_id"], lambda: ran.append(1) or ready_notices.run_check(lane, "schedule"))
        handle = lane.runner.client.get_schedule_handle(schedule_id)
        lane.runner.call(handle.trigger())  # do not wait an hour: run the tick now
        deadline = time.monotonic() + 20
        while not ran and time.monotonic() < deadline:
            time.sleep(0.2)
        assert ran and lane.records.load("readiness_check", "latest")["by"] == "schedule"
        lane.runner.call(handle.delete())
    finally:
        orchestrate.close_lane(lane)
