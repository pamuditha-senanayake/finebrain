# test_marks.py: step 15 slice 3, Mark as wrong on Finebase HQ. The note stays on the run and its row, the agent's DRI
# is told, it is audited and counted for the agent in the week it was marked, and five in a week raise a trend.
# Uses: app/api/run_marks.py, learn_routes.py, views.py, tests/test_api.py (the hq fixture), tests/test_spike.py, test_counts.py.
from app.pipeline.store_counts import MemoryCounts
from tests.test_api import FOUNDER, STEWARD, TENANT, get, hq  # noqa: F401  (hq is the fixture)
from tests.test_counts import WEEK
from tests.test_spike import send_refund

# Config
WRONG = ("Marked wrong", "Refund worker, email")
NOTE = "Refunded the full amount, but the customer had used the service for two months."


# --- Helpers

def mark(client, run_id: str, note: str = NOTE, persona: str = STEWARD):
    return client.post(f"/api/t/{TENANT}/ops/markRunWrong", json={"runId": run_id, "note": note}, headers={"x-persona": persona})


def first_run(lane) -> str:
    return lane.records.list_kind("run")[0]["run_id"]


# --- Marking

def test_the_note_stays_on_the_run_and_its_row(hq):
    client, lane, _ = hq
    run_id = first_run(lane)
    get(client, "runs")  # the row is built and kept before the mark
    assert mark(client, run_id).json() == {"ok": True}
    detail = get(client, f"runs/{run_id}").json()
    assert (detail["markedWrong"]["by"], detail["markedWrong"]["note"], detail["failureClass"], detail["humanTouch"]) == (STEWARD, NOTE, "marked wrong", True)
    row = next(r for r in get(client, "runs").json() if r["id"] == run_id)
    assert row["markedWrong"]["note"] == NOTE


def test_the_agents_dri_is_told_and_it_is_audited(hq):
    client, lane, _ = hq
    mark(client, first_run(lane))
    told = [n for n in lane.records.list_kind("notification") if n["title"].startswith("Marked wrong")]
    assert [(n["to"], n["href"]) for n in told] == [(FOUNDER, f"/l3/runs/{first_run(lane)}")] and NOTE in told[0]["body"]
    assert [e["body"]["by"] for e in lane.audit.in_order() if e["topic"] == "run.marked_wrong"] == [STEWARD]


def test_a_run_is_marked_once_and_only_with_a_note(hq):
    client, lane, _ = hq
    assert mark(client, first_run(lane), "  ").status_code == 409
    assert mark(client, first_run(lane)).status_code == 200 and mark(client, first_run(lane), persona=FOUNDER).status_code == 409
    assert mark(client, "run_nothing").status_code == 404


# --- Counting

def test_it_counts_for_the_agent_in_the_week_it_was_marked(hq):
    client, lane, _ = hq
    lane.counts = MemoryCounts()
    mark(client, first_run(lane))
    assert lane.counts.weeks(*WRONG) == {WEEK: 1} and lane.counts.cases_of(*WRONG, WEEK) == [first_run(lane)]


def test_five_marked_in_a_quiet_week_raise_a_trend(hq):
    client, lane, _ = hq
    for index in range(3):
        send_refund(client, lane, f"mail_wrong_{index}")
    lane.counts = MemoryCounts()  # a quiet past for marks
    for run in lane.records.list_kind("run"):
        mark(client, run["run_id"])
    card = next(t for t in get(client, "trends").json() if t["metric"] == "Marked wrong")
    assert (card["segment"], card["latest"], card["ownerId"]) == ("Refund worker, email", 5, FOUNDER)
