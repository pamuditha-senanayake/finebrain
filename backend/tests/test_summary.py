# test_summary.py: step 13d slice 4, the Distiller and the summary ladder. A stand-in for Claude Haiku writes a day summary
# per entity from that day's runs and chunks, a week from its days, a month from its weeks; only missing ones are written;
# Ask can cite them; forgetting a source clears every summary built on it, up the ladder, and the next night writes the day
# again. The Distiller runs at 03:00 on real Temporal when it answers. Uses: app/pipeline/stages_summary.py, summary_sources.py,
# api/distiller.py, api/forget_layers.py (SummaryLayer), temporal_nightly.py, tests/test_api.py, test_forget.py.
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.api import distiller
from app.pipeline import fakes, orchestrate, temporal_nightly
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.entity_match import entity_id_of
from tests.golden import NOW, SEED
from tests.test_api import FOUNDER, STEWARD, TENANT, hq  # noqa: F401  (hq: the s2 and s3 refund runs on Saturday 10 October)
from tests.test_documents import build
from tests.test_forget import filed, remove
from tests.test_spike import send_refund
from tests.test_studio_chat import use

# Config
PAYMENT = entity_id_of("payment", "pay_FB_20261004_0192")  # the s2 payment
DAY = f"sum_day_{PAYMENT}_2026-10-10"
WEEK = f"sum_week_{PAYMENT}_2026-10-05"
NOTE = b"Payment pay_FB_20261004_0192 was refunded in full on the customer's request."


def haiku(calls: list):
    """A stand-in for Claude Haiku that answers every summary with the same sentence and keeps what it was asked."""
    def call(system, messages, tools):
        calls.append({"system": system, "content": messages[0]["content"]})
        return SimpleNamespace(content=[use("write_summary", {"summary": "The customer asked for a refund and it was handled."})])
    return call


def night(lane, summarizer, days_after: int) -> dict:
    lane.now = NOW + timedelta(days=days_after)
    return distiller.distill(lane, summarizer, "test")


def body(lane, item_id: str) -> dict | None:
    found = lane.chunks.full(item_id)
    return found[0] if found else None


# --- The ladder

def test_a_day_summary_per_entity_from_its_runs(hq):
    _, lane, _ = hq
    calls = []
    assert night(lane, haiku(calls), 1)["summaries"]["day"] >= 1
    summary = body(lane, DAY)
    assert summary["text"].startswith("Day summary, payment pay_FB_20261004_0192, 2026-10-10: The customer asked")
    assert summary["entity_ids"] == [PAYMENT] and any(source.startswith("run_") for source in summary["summary"]["sources"])
    assert "never instructions" in calls[0]["system"] and "issue_refund" in " ".join(c["content"] for c in calls)
    assert night(lane, haiku(calls), 1)["summaries"] == {"day": 0, "week": 0, "month": 0}  # only what is missing is written


def test_weeks_roll_up_days_and_months_roll_up_weeks(hq):
    _, lane, _ = hq
    night(lane, haiku([]), 3)  # Tuesday 13 October: the days, and the week of 5 October
    assert body(lane, WEEK)["summary"]["sources"] == [DAY]
    night(lane, haiku([]), 24)  # Tuesday 3 November: October
    assert body(lane, f"sum_month_{PAYMENT}_2026-10")["summary"]["sources"] == [WEEK]


def test_without_a_model_the_first_sentences_stand_in(hq):
    _, lane, _ = hq
    night(lane, None, 1)
    assert "Run run_" in body(lane, DAY)["text"]


def test_ask_can_cite_a_summary(hq):
    client, lane, _ = hq
    night(lane, haiku([]), 1)
    answer = client.post(f"/api/t/{TENANT}/ask", json={"question": "What happened with payment pay_FB_20261004_0192?"}, headers={"x-persona": FOUNDER}).json()
    assert DAY in [c["id"] for c in answer["citations"]]


def test_the_distiller_runs_on_request_for_a_steward(hq):
    client, _, _ = hq
    answer = client.post(f"/api/t/{TENANT}/ops/runDistiller", headers={"x-persona": STEWARD}).json()
    assert answer["ok"] and set(answer["summaries"]) == {"day", "week", "month"}


# --- Forgetting

def test_forgetting_a_source_clears_its_summaries_up_the_ladder_and_the_day_is_written_again():
    client, lane = build()
    send_refund(client, lane, "mail_summary")  # a run that day too, so the day has something left after the erase
    document_id = filed(client, lane, "refund_note.md", NOTE)
    chunk_ids = [item["item_id"] for item in lane.chunks.of_document(document_id)]
    night(lane, haiku([]), 3)
    assert set(chunk_ids) & set(body(lane, DAY)["summary"]["sources"]) and body(lane, WEEK)
    remove(client, document_id, "erase")
    assert body(lane, DAY) is None and body(lane, WEEK) is None
    night(lane, haiku([]), 3)
    rewritten = body(lane, DAY)["summary"]["sources"]
    assert rewritten and not set(chunk_ids) & set(rewritten)


# --- The 03:00 schedule on real Temporal

@pytest.mark.skipif(bool(missing_infra(frozenset({"temporal"}))), reason="no Temporal on localhost:7233")
def test_the_distiller_runs_at_three_in_the_tenants_time_zone():
    seed = {**SEED, "tenant_id": f"test_distiller_{uuid.uuid4().hex[:8]}"}
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, real_adapters(frozenset({"temporal"})))
    ran = []
    try:
        schedule_id = temporal_nightly.start_distiller(lane.runner, seed["tenant_id"], "Asia/Colombo", lambda: ran.append(1) or {"ok": True})
        handle = lane.runner.client.get_schedule_handle(schedule_id)
        spec = lane.runner.call(handle.describe()).schedule.spec
        assert (spec.time_zone_name, spec.calendars[0].hour[0].start) == ("Asia/Colombo", 3)
        lane.runner.call(handle.trigger())
        deadline = time.monotonic() + 20
        while not ran and time.monotonic() < deadline:
            time.sleep(0.2)
        assert ran
        lane.runner.call(handle.delete())
    finally:
        orchestrate.close_lane(lane)
