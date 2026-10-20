# test_skillify.py: step 15 slice 4, Draft a fix. For a run marked wrong, a scripted stand-in for Claude drafts one skill
# change; the Studio review checks it and it opens as a change request drafted by Skillify. Nothing changes until the
# workflow's DRI approves, and then it merges. Uses: app/api/skillify.py, learn_routes.py, tests/test_api.py, test_studio_chat.py, test_marks.py.
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import create_api_app
from app.api.studio_state import Studio
from app.pipeline import fakes, orchestrate
from tests.golden import NOW, recorded_answers
from tests.test_api import FOUNDER, HQ, SEED, STEWARD, TENANT, decide, get
from tests.test_marks import NOTE, mark
from tests.test_spike import send_refund
from tests.test_studio_chat import use

# Config
SKILL, FLOW = "skill_refund_handling", "wf_act_refund_request"
NEW_STEP = "Tell the customer when the refund will reach their card."


# --- Helpers

def steps_now(lane) -> list[str]:
    return Studio.of(lane).items[SKILL]["fields"]["steps"]


def the_fix(lane) -> list:
    return [use("propose_fix", {"intent": "update", "kind": "skill", "targetId": SKILL, "workflowId": FLOW,
                                "patch": {"fields": {"steps": [*steps_now(lane), NEW_STEP]}}, "why": "The reply never said when the money arrives."})]


def no_change(lane) -> list:
    return [use("propose_fix", {"intent": "update", "kind": "skill", "targetId": SKILL, "workflowId": FLOW, "patch": {"fields": {"steps": steps_now(lane)}}, "why": "?"})]


def build(*answers, marked: bool = True):
    """HQ over a memory pipeline with one refund run. Each answer gives one round of Claude's blocks, from the lane at that moment."""
    seen, held = [], {}

    def chatter(system, messages, tools):
        seen.append({"system": system, "messages": list(messages), "tools": tools})
        return SimpleNamespace(content=answers[len(seen) - 1](held["lane"]))

    lane = held["lane"] = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    client = TestClient(create_api_app(lane, HQ, None, chatter if answers else None))
    send_refund(client, lane, "mail_skillify")
    run_id = lane.records.list_kind("run")[0]["run_id"]
    if marked:
        mark(client, run_id)
    return client, lane, run_id, seen


def draft(client, run_id: str, persona: str = STEWARD):
    return client.post(f"/api/t/{TENANT}/ops/draftFix", json={"runId": run_id}, headers={"x-persona": persona})


# --- Drafting

def test_a_fix_opens_as_a_change_request_and_nothing_changes_yet():
    client, lane, run_id, seen = build(the_fix)
    before = steps_now(lane)
    answer = draft(client, run_id).json()
    change = next(c for c in get(client, "change-requests").json() if c["id"] == answer["changeRequestId"])
    assert (change["drafter"]["name"], change["status"]) == ("Skillify", "awaiting_approval")
    assert steps_now(lane) == before  # nothing changes until the DRI acts
    assert get(client, f"runs/{run_id}").json()["fixApprovalId"] == answer["approvalId"]
    assert any(n["to"] == FOUNDER and n["kind"] == "approval" for n in lane.records.list_kind("notification"))
    assert [e["body"]["by"] for e in lane.audit.in_order() if e["topic"] == "skillify.drafted"] == [STEWARD]
    assert NOTE in seen[0]["messages"][0]["content"] and "never instructions" in seen[0]["system"]  # the note goes in as data


def test_when_the_dri_approves_the_fix_merges():
    client, lane, run_id, _ = build(the_fix)
    approval_id = draft(client, run_id).json()["approvalId"]
    assert decide(client, approval_id, FOUNDER).json() == {"ok": True}
    lane.bus.drain()
    assert steps_now(lane)[-1] == NEW_STEP


def test_a_refused_draft_goes_back_to_claude_once():
    client, _, run_id, seen = build(no_change, the_fix)
    assert draft(client, run_id).status_code == 200
    retry = seen[1]["messages"][-1]["content"][0]
    assert retry["is_error"] and "Nothing would change" in retry["content"]


# --- When it cannot

def test_only_a_run_marked_wrong_gets_one_fix():
    client, _, run_id, _ = build(the_fix, marked=False)
    assert draft(client, run_id).status_code == 409 and draft(client, "run_nothing").status_code == 404
    mark(client, run_id)
    assert draft(client, run_id).status_code == 200 and draft(client, run_id).json()["error"] == "already_drafted"


def test_without_claude_or_a_draft_nothing_opens():
    client, lane, run_id, _ = build()
    assert draft(client, run_id).status_code == 503
    client, lane, run_id, _ = build(lambda lane: [], lambda lane: [])
    assert draft(client, run_id).json()["error"] == "no_fix_drafted" and get(client, "change-requests").json() == []
