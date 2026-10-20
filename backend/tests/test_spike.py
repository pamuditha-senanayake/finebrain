# test_spike.py: step 15 slice 2, the spike check. A week is unusual at 3 times the usual (the median of the 12 weeks
# before) and at least 5; the owner is told once and it is audited; the card keeps up with the week; Mark as known quiets it.
# Uses: app/pipeline/stages_spike.py, api/learn_routes.py, api/trend_views.py, tests/test_api.py (the hq fixture), tests/golden.py.
from datetime import timedelta

from app.pipeline import capture_api, stages_spike
from app.pipeline.store_counts import MemoryCounts
from tests.golden import NOW, RAW
from tests.test_api import FOUNDER, SEED, STEWARD, TENANT, get, hq  # noqa: F401  (hq is the fixture)
from tests.test_counts import REQUESTS, WEEK

# Config
S2 = "s2_refund_monthly_in_policy"


# --- Helpers

def usual_weeks(lane, value: int) -> None:
    """Twelve ordinary weeks before WEEK, all at this value."""
    for back in range(1, 13):
        lane.counts.add_sample(*REQUESTS, WEEK - timedelta(weeks=back), value)


def this_week(lane, count: int) -> None:
    for index in range(count):
        lane.counts.add(*REQUESTS, WEEK, f"run_{index}")


def send_refund(client, lane, external_id: str) -> None:
    """One more s2 refund email through capture, as a new message."""
    body = RAW[S2]["raw_body"].encode()
    headers = {"content-type": "message/rfc822", "x-external-id": external_id, "x-signature": capture_api.sign(SEED["connectors"]["conn_gmail_support"]["secret"], body)}
    assert client.post("/capture/conn_gmail_support", content=body, headers=headers).status_code == 202
    lane.bus.drain()


def mark_known(client, trend_id: str):
    return client.post(f"/api/t/{TENANT}/ops/markTrendKnown", json={"id": trend_id}, headers={"x-persona": STEWARD})


def told(lane) -> list[dict]:
    return [n for n in lane.records.list_kind("notification") if n["title"].startswith("Unusual week")]


# --- What counts as unusual

def test_three_times_the_usual_and_at_least_five_is_unusual(hq):
    _, lane, _ = hq
    lane.counts = MemoryCounts()
    usual_weeks(lane, 2)
    this_week(lane, 6)
    trend = stages_spike.check_series(lane, *REQUESTS, NOW)
    assert (trend.usual, trend.latest, trend.ratio, trend.owner_id) == (2.0, 6, 3.0, FOUNDER)
    assert trend.weeks == [2] * 11 + [6] and len(trend.case_ids) == 6


def test_a_quiet_series_and_a_small_rise_stay_quiet(hq):
    _, lane, _ = hq
    for usual, latest in ((1, 4), (2, 5)):  # 4x but under 5; 5 but only 2.5x
        lane.counts = MemoryCounts()
        usual_weeks(lane, usual)
        this_week(lane, latest)
        assert stages_spike.check_series(lane, *REQUESTS, NOW) is None


def test_the_owner_of_an_escalation_series_is_its_agents_dri(hq):
    _, lane, _ = hq
    assert stages_spike.owner_of(lane, "Escalations", "Refund worker, email") == FOUNDER
    assert stages_spike.owner_of(lane, "Requests", "Nothing we know, chat") == FOUNDER  # the first L1


# --- Through the pipeline

def test_the_run_that_makes_the_spike_tells_the_owner_once_and_the_card_keeps_up(hq):
    client, lane, _ = hq
    lane.counts = MemoryCounts()  # a quiet past: every week before was 0
    for index in range(4):
        send_refund(client, lane, f"mail_spike_{index}")
    assert get(client, "trends").json() == [] and told(lane) == []
    send_refund(client, lane, "mail_spike_4")
    send_refund(client, lane, "mail_spike_5")
    card = get(client, "trends").json()[0]
    assert (card["metric"], card["segment"], card["latest"], card["status"], len(card["weeks"])) == ("Requests", "Refund handling, email", 6, "new", 12)
    assert [n["to"] for n in told(lane)] == [FOUNDER]
    assert [e["topic"] for e in lane.audit.in_order() if e["topic"].startswith("trend.")] == ["trend.found"]


# --- Mark as known

def test_mark_as_known_quiets_the_week(hq):
    client, lane, _ = hq
    lane.counts = MemoryCounts()
    this_week(lane, 5)
    trend = stages_spike.check_series(lane, *REQUESTS, NOW)
    assert mark_known(client, trend.trend_id).json() == {"ok": True}
    assert get(client, "trends").json()[0]["status"] == "known"
    assert mark_known(client, trend.trend_id).status_code == 409 and mark_known(client, "tr_nothing").status_code == 404
    this_week(lane, 8)  # more of the same week: still quiet
    assert stages_spike.check_series(lane, *REQUESTS, NOW) is None and get(client, "trends").json()[0]["status"] == "known"
    assert [e["topic"] for e in lane.audit.in_order() if e["topic"].startswith("trend.")] == ["trend.found", "trend.marked_known"]
