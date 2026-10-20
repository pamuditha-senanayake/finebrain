# test_counts.py: step 15 slice 1, S13's weekly counts. Each finished run counts once in its week (requests per skill,
# escalations per agent, by channel), sample history fills a new tenant's past without hiding real counts, and runs
# recorded earlier are back-filled. Runs on memory, and on Postgres when it answers.
# Uses: app/pipeline/stages_learn.py, store_counts.py, api/learn_routes.py, tests/test_api.py (the hq fixture).
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.pipeline import stages_learn, store_postgres
from app.pipeline.store_counts import MemoryCounts, PostgresCounts
from tests.test_api import hq  # noqa: F401  (the fixture: s2 resolved, s3 waiting for approval)

# Config
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")
WEEK = date(2026, 10, 5)  # the golden runs happen on Saturday 10 October, Colombo time
REQUESTS, ESCALATIONS = ("Requests", "Refund handling, email"), ("Escalations", "Refund worker, email")
SAMPLE = {"weeks_ending": "2026-10-05", "series": [{"metric": "Requests", "segment": "Refund handling, email", "weeks": [3, 2, 4]}]}


# --- Weeks

def test_a_week_starts_on_monday_in_the_tenants_time_zone():
    sunday_night = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)  # already Monday 01:30 in Colombo
    assert stages_learn.week_of(sunday_night, "Asia/Colombo") == date(2026, 10, 12)
    assert stages_learn.week_of(sunday_night, "UTC") == WEEK


# --- Counting runs

def test_each_finished_run_counts_once_on_top_of_the_sample_week(hq):
    _, lane, _ = hq
    runs = sorted(run["run_id"] for run in lane.records.list_kind("run"))
    assert lane.counts.weeks(*REQUESTS)[WEEK] == 2 + 2  # the sample said 2; s2 and s3 add one each
    assert lane.counts.cases_of(*REQUESTS, WEEK) == runs
    assert lane.counts.weeks(*ESCALATIONS)[WEEK] == 1 + 1  # s3 waits for a person
    assert stages_learn.count_existing(lane) == 0  # a redelivery or a restart counts nothing twice


def test_runs_recorded_before_counting_are_back_filled(hq):
    _, lane, _ = hq
    lane.counts = MemoryCounts()
    assert stages_learn.count_existing(lane) == 3  # s2: requests; s3: requests and escalations
    assert lane.counts.weeks(*REQUESTS) == {WEEK: 2}


def test_a_run_whose_trace_is_gone_counts_under_unknown_channel(hq):
    _, lane, _ = hq
    run = {**lane.records.list_kind("run")[0], "run_id": "run_lost", "trace_object_uri": "pending:run_lost"}
    assert stages_learn.count_run(lane, run) == [("Requests", "Refund handling, unknown channel")]
    assert lane.counts.cases_of("Requests", "Refund handling, unknown channel", WEEK) == ["run_lost"]


# --- Sample history

def test_sample_history_fills_the_weeks_before_and_never_hides_a_real_count():
    lane = SimpleNamespace(counts=MemoryCounts())
    lane.counts.add(*REQUESTS, WEEK, "run_real")
    assert stages_learn.load_sample(lane, SAMPLE) == 3
    assert lane.counts.weeks(*REQUESTS) == {date(2026, 9, 21): 3, date(2026, 9, 28): 2, WEEK: 1}
    assert stages_learn.load_sample(lane, {}) == 0


# --- Postgres

@NEEDS_POSTGRES
def test_postgres_gives_the_same_answers_as_memory():
    stores = [MemoryCounts(), PostgresCounts(store_postgres.connect(), f"t_counts_{uuid.uuid4().hex[:8]}")]
    for store in stores:
        assert store.add(*REQUESTS, WEEK, "run_a") and store.add(*REQUESTS, WEEK, "run_b")
        assert not store.add(*REQUESTS, WEEK, "run_a")
        store.add_sample(*REQUESTS, WEEK, 9)
        store.add_sample(*ESCALATIONS, date(2026, 9, 28), 4)
    memory, postgres = stores
    assert postgres.series() == memory.series() == [ESCALATIONS, REQUESTS]
    assert postgres.weeks(*REQUESTS) == memory.weeks(*REQUESTS) == {WEEK: 2}
    assert postgres.weeks(*ESCALATIONS) == memory.weeks(*ESCALATIONS) == {date(2026, 9, 28): 4}
    assert postgres.cases_of(*REQUESTS, WEEK) == memory.cases_of(*REQUESTS, WEEK) == ["run_a", "run_b"]
