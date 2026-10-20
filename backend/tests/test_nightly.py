# test_nightly.py: step 15 slice 5, the nightly review. Runs marked wrong are grouped (a stand-in for Claude Opus), one fix
# is drafted per group (a stand-in for Claude Sonnet): a C0 or C1 fix is applied at once, the rest wait for the DRI. The
# digest counts runs and failures by type, lists what was fixed, drafted and is waiting, and the leaders hear of it. The 02:00
# schedule runs on real Temporal when it answers. Uses: app/api/nightly.py, nightly_groups.py, skillify.py, temporal_nightly.py, tests/test_skillify.py.
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import nightly, nightly_groups
from app.api.routes import create_api_app
from app.api.studio_state import Studio
from app.pipeline import fakes, orchestrate, temporal_nightly
from app.pipeline.adapters import missing_infra, real_adapters
from tests.golden import NOW, recorded_answers
from tests.test_api import FOUNDER, HQ, SEED, STEWARD, TENANT, get
from tests.test_marks import mark
from tests.test_skillify import FLOW, SKILL, the_fix
from tests.test_spike import send_refund
from tests.test_studio_chat import use

# Config
NOTES = ["The reply never said when the money arrives.", "No arrival date for the refund in the reply.", "Refunded a payment from a different customer."]


# --- Helpers

def reworded(lane) -> list:
    return [use("propose_fix", {"intent": "update", "kind": "skill", "targetId": SKILL, "workflowId": FLOW,
                                "patch": {"topics": ["refunds", "payment owner"]}, "why": "Tag it so wrong-customer cases find it."})]  # C1: applied at once


def stand_in(*answers, seen: list):
    """A scripted Claude: each call answers with the next round's blocks, built from the lane."""
    def call(system, messages, tools):
        seen.append({"system": system, "messages": list(messages), "tools": tools})
        return SimpleNamespace(content=answers[len(seen) - 1](held["lane"]))
    held = {}
    return call, held


def build(groups: list[list[int]] | None, *fixes):
    """HQ with three refund runs marked wrong, Opus scripted to give these groups (by run index), Sonnet these fixes."""
    drafts, grouped = [], []
    drafter, held = stand_in(*fixes, seen=drafts)
    lane = held["lane"] = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    client = TestClient(create_api_app(lane, HQ, None, drafter if fixes else None))
    for index, note in enumerate(NOTES):
        send_refund(client, lane, f"mail_night_{index}")
    runs = sorted((r for r in lane.records.list_kind("run")), key=lambda r: r["run_id"])
    for run, note in zip(runs, NOTES):
        mark(client, run["run_id"], note)
    ids = [r["run_id"] for r in runs]
    answer = [use("group_wrong_runs", {"groups": [{"title": f"Group {n}", "run_ids": [ids[i] for i in g]} for n, g in enumerate(groups)]})] if groups else []
    lane.resolve, held_grouper = stand_in(lambda _: answer, seen=grouped)
    held_grouper["lane"] = lane
    return client, lane, ids, drafts, grouped


def run_review(client):
    return client.post(f"/api/t/{TENANT}/ops/runOvernightReview", headers={"x-persona": STEWARD})


def kinds(digest: dict) -> list[str]:
    return [i["kind"] for i in digest["items"] if i["kind"] in ("auto_fix", "drafted")]


# --- The review

def test_one_fix_per_group_a_low_one_applied_and_the_rest_drafted():
    client, lane, ids, drafts, grouped = build([[0, 1], [2]], the_fix, reworded)
    assert get(client, "digest").json() is None
    assert run_review(client).json()["ok"]
    digest = get(client, "digest").json()
    assert kinds(digest) == ["drafted", "auto_fix"] and len(drafts) == 2
    assert all(note in grouped[0]["messages"][0]["content"] for note in NOTES)
    assert NOTES[1] in drafts[0]["messages"][0]["content"]  # one draft sees every note of its group
    assert Studio.of(lane).items[SKILL]["topics"] == ["refunds", "payment owner"]  # applied at once
    cr = [lane.records.load("skillify", i)["cr_id"] for i in ids]
    assert cr[0] == cr[1] and cr[0] is not None and cr[2] is None
    assert [e["topic"] for e in lane.audit.in_order() if e["topic"].startswith("skillify.")] == ["skillify.drafted", "skillify.applied"]


def test_the_digest_counts_failures_and_the_leaders_hear_of_it():
    client, lane, _, _, _ = build([[0, 1, 2]], the_fix)
    run_review(client)
    digest = get(client, "digest").json()
    assert (digest["date"], digest["runs"], digest["failures"], digest["failureClasses"]) == ("2026-10-10", 3, 3, [{"name": "marked wrong", "count": 3}])
    assert any(i["kind"] == "waiting" and i["href"].startswith("/l1/approvals/") for i in digest["items"])  # the drafted fix waits for its DRI
    assert [n["to"] for n in lane.records.list_kind("notification") if n["kind"] == "digest"] == [FOUNDER]
    assert [e["topic"] for e in lane.audit.in_order() if e["topic"] == "nightly.reviewed"] == ["nightly.reviewed"]


def test_a_second_night_does_not_draft_again_and_without_claude_it_still_reports():
    client, lane, _, drafts, _ = build([[0, 1, 2]], the_fix)
    run_review(client)
    run_review(client)
    assert len(drafts) == 1 and get(client, "digest").json()["failures"] == 0  # nothing new was marked since
    client, _, _, _, _ = build(None)
    run_review(client)
    digest = get(client, "digest").json()
    assert digest["failures"] == 3 and kinds(digest) == []


def test_times_stored_by_postgres_are_read():
    assert nightly.moment("2026-10-20T04:34:11.415280Z") == nightly.moment("2026-10-20T04:34:11.415280+00:00")


def test_groups_that_do_not_hold_together_fall_back_to_one_each():
    marks = [{"run_id": "a", "note": "x"}, {"run_id": "b", "note": "y"}]
    runs = {"a": {"agent_id": "g", "outcome": "resolved"}, "b": {"agent_id": "g", "outcome": "resolved"}}
    made_up = lambda *_: SimpleNamespace(content=[use("group_wrong_runs", {"groups": [{"title": "t", "run_ids": ["a", "c"]}]})])
    assert nightly_groups.group(made_up, marks, runs) == nightly_groups.one_each(marks)
    assert [g["run_ids"] for g in nightly_groups.group(None, marks, runs)] == [["a"], ["b"]]


# --- The 02:00 schedule on real Temporal

@pytest.mark.skipif(bool(missing_infra(frozenset({"temporal"}))), reason="no Temporal on localhost:7233")
def test_the_schedule_runs_at_two_in_the_tenants_time_zone():
    seed = {**SEED, "tenant_id": f"test_nightly_{uuid.uuid4().hex[:8]}"}
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, real_adapters(frozenset({"temporal"})))
    ran = []
    try:
        schedule_id = temporal_nightly.start(lane.runner, seed["tenant_id"], "Asia/Colombo", lambda: ran.append(1) or {"date": "2026-10-10"})
        handle = lane.runner.client.get_schedule_handle(schedule_id)
        spec = lane.runner.call(handle.describe()).schedule.spec
        assert (spec.time_zone_name, spec.calendars[0].hour[0].start, spec.calendars[0].minute[0].start) == ("Asia/Colombo", 2, 0)  # the server keeps cron as calendars
        lane.runner.call(handle.trigger())  # do not wait for 02:00
        deadline = time.monotonic() + 20
        while not ran and time.monotonic() < deadline:
            time.sleep(0.2)
        assert ran
        lane.runner.call(handle.delete())
    finally:
        orchestrate.close_lane(lane)
