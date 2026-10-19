# test_lists_query.py: step 12, lists of thousands. The server filters, searches, sorts and pages: a page, the total,
# the position of a target row, the matches, and the count behind each filter value. Ten thousand runs answer fast.
# Uses: app/api/lists_query.py, lists_rows.py, routes.py, scripts/seed_runs.py, tests/golden.py.
import time

import pytest
from fastapi.testclient import TestClient

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import fakes, orchestrate
from scripts.seed_runs import add_runs
from tests.golden import NOW

# Config
SEED, HQ = load_hq()
TENANT = SEED["tenant_id"]
FOUNDER = "h-pamuditha"
BIG = 10_000
QUICK = 1.0  # seconds: the plan's bar for finding one run among ten thousand


def build(count: int):
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    add_runs(lane, count)
    return TestClient(create_api_app(lane, HQ)), lane


def page(client, name: str, **query) -> dict:
    response = client.get(f"/api/t/{TENANT}/lists/{name}", params=query, headers={"x-persona": FOUNDER})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def small():
    return build(300)[0]


def test_a_page_has_the_total_and_keeps_newest_first(small):
    first = page(small, "runs", limit=50)
    assert (first["total"], first["offset"], len(first["items"])) == (300, 0, 50)
    assert [r["id"] for r in first["items"][:2]] == ["run_00000", "run_00001"]
    assert page(small, "runs", limit=50, offset=250)["items"][-1]["id"] == "run_00299"
    assert page(small, "runs", limit=50, sort="costUsd:asc")["total"] == 300


def test_filters_narrow_and_facets_count_each_value_against_the_other_filters(small):
    filtered = page(small, "runs", status="escalated")
    assert filtered["total"] == 50 and {r["status"] for r in filtered["items"]} == {"escalated"}
    both = page(small, "runs", status="escalated,failed", agentId="agent_refund_worker")
    assert both["total"] == sum(1 for i in range(300) if i % 3 == 0 and i % 6 in (3, 4))
    assert filtered["facets"]["status"]["escalated"] == 50 and sum(filtered["facets"]["agentId"].values()) == 50  # agents among the escalated ones
    assert sum(page(small, "runs")["facets"]["status"].values()) == 300


def test_search_finds_without_hiding_and_reports_where_the_matches_sit(small):
    found = page(small, "runs", q="case 00123")
    assert found["total"] == 300 and found["matches"]["total"] == 1 and found["matches"]["positions"] == [123]
    assert page(small, "runs", q="no such words")["matches"] == {"total": 0, "positions": []}


def test_around_lands_on_the_page_that_holds_the_row(small):
    landed = page(small, "runs", around="run_00237", limit=100)
    assert (landed["position"], landed["offset"]) == (237, 200) and any(r["id"] == "run_00237" for r in landed["items"])
    assert page(small, "runs", around="run_missing")["position"] is None


def test_other_lists_page_the_same_way(small):
    assert page(small, "escalations")["total"] == 100  # escalated and awaiting approval
    assert page(small, "documents")["total"] == 0 and page(small, "audit")["items"] == []
    assert small.get(f"/api/t/{TENANT}/lists/nothing", headers={"x-persona": FOUNDER}).status_code == 404


def test_one_run_among_ten_thousand_is_found_inside_a_second():
    client, _ = build(BIG)
    page(client, "runs", limit=100)  # the first call builds every row once
    started = time.perf_counter()
    landed = page(client, "runs", around="run_07311", q="case 07311", limit=100)
    elapsed = time.perf_counter() - started
    assert landed["position"] == 7311 and landed["matches"]["positions"] == [7311] and landed["total"] == BIG
    assert elapsed < QUICK, f"{elapsed:.2f}s"
    started = time.perf_counter()
    page(client, "runs", status="escalated", agentId="agent_billing_worker", limit=100)
    assert time.perf_counter() - started < QUICK
