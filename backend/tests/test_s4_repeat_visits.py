# test_s4_repeat_visits.py: S4 when one chat reaches it more than once, as in the full refund BDD.
# Visit 1: "I want a refund for my last order" starts the run and hands the chat to the Refund agent.
# Visit 2: "yes, that one" joins that open run: no new recipe pick, no second handoff.
# Visit 3: a message after the run closed starts a fresh run. Other agents and other chats never share a run.
# Uses: stages_orchestrate.py, stages_record.py, contracts_start.py, tests/test_s4_orchestrate_bdd.py (helpers), test_s1_refund_bdd.py.
import json
import random

import pytest

from app.pipeline import observe, stages_record
from app.pipeline.contracts_signal import VersionRef
from app.pipeline.contracts_start import RunContinued, RunStarted
from tests.golden import NOW
from tests.test_s1_refund_bdd import CONFIRM, REFUND_ASK, poll, portal_message, shop as s1_shop
from tests.test_s4_orchestrate_bdd import k3, published, start

# Config
shop = s1_shop  # "Given the shop website chat is connected", shared with S1
ANOTHER_ASK = "I want a refund for another order too"
BILLING = {"agent_id": "agent_billing_helper", "activity_id": "act_billing_question", "resolver_rule_id": "rr_billing_question",
           "skill_ref": VersionRef(id="skill_billing_answers", version=1, branch="main", commit_id="cmt_0003")}
BEN = {"conversation_id": "c-2", "conversations": {"customer_id": "cust-ben"}}


def says(lane, inbox, body: str, **who) -> str:
    """One more chat message through the real S1 and S2, at a later time. Returns its K2 signal id."""
    inbox.append(portal_message(len(inbox) + 1, body, **who))
    poll(lane)
    lane.bus.drain()
    return lane.records.list_kind("signal")[-1]["signal_id"]


def close_run(lane, run_id: str, outcome: str) -> None:
    """S10 closes (or pauses) the run, as the recorder saves it from runs.completed."""
    started = next(run for run in lane.records.list_kind("run_started") if run["run_id"] == run_id)
    record, _ = stages_record.record(k3(started["signal_id"]), None, [], outcome, None, lane.seed, NOW, NOW, run_id=run_id)
    lane.records.save("run", run_id, record)


def continued(lane) -> list[RunContinued]:
    return [RunContinued.model_validate(payload) for payload in published(lane, "runs.continued")]


# --- Visit 2 joins the open run

def test_visit_2_the_confirmation_joins_the_open_refund_run(shop):
    lane, inbox = shop
    ask = says(lane, inbox, REFUND_ASK)
    first = start(lane, k3(ask))
    confirm = says(lane, inbox, CONFIRM)
    assert start(lane, k3(confirm)) is None  # no new run for S5 to S10
    [joined] = continued(lane)
    assert joined.run_id == first.run_id and joined.agent_id == "agent_refund_worker" and joined.request_text == CONFIRM
    assert joined.transcript_signal_ids == [ask, confirm]
    assert len(published(lane, "runs.started")) == 1  # one recipe pick, one handoff


def test_visit_2_while_the_run_waits_for_approval_still_joins_it(shop):
    lane, inbox = shop
    first = start(lane, k3(says(lane, inbox, REFUND_ASK)))
    close_run(lane, first.run_id, "awaiting_approval")
    start(lane, k3(says(lane, inbox, CONFIRM)))
    assert [joined.run_id for joined in continued(lane)] == [first.run_id]


def test_the_same_visit_delivered_twice_joins_once(shop):
    lane, inbox = shop
    start(lane, k3(says(lane, inbox, REFUND_ASK)))
    confirm = says(lane, inbox, CONFIRM)
    start(lane, k3(confirm))
    start(lane, k3(confirm))
    assert len(continued(lane)) == 1


# --- Visit 3 after the run closed starts fresh

@pytest.mark.parametrize("outcome", ["resolved", "escalated", "failed", "blocked", "abandoned"])
def test_visit_3_after_the_run_closed_starts_a_fresh_run(shop, outcome):
    lane, inbox = shop
    ask = says(lane, inbox, REFUND_ASK)
    first = start(lane, k3(ask))
    confirm = says(lane, inbox, CONFIRM)
    start(lane, k3(confirm))
    close_run(lane, first.run_id, outcome)
    again = says(lane, inbox, ANOTHER_ASK)
    second = start(lane, k3(again))
    assert second.run_id != first.run_id and second.recipe.skill_ref.id == "skill_refund_handling"
    assert second.handoff.transcript_signal_ids == [ask, confirm, again]  # the new run still sees the whole chat


# --- Other agents and other chats never share a run

def test_a_billing_question_mid_refund_gets_its_own_run_and_the_refund_continues(shop):
    lane, inbox = shop
    refund = start(lane, k3(says(lane, inbox, REFUND_ASK)))
    billing = start(lane, k3(says(lane, inbox, "Also, why was I charged twice?"), **BILLING))
    start(lane, k3(says(lane, inbox, CONFIRM)))
    assert billing.run_id != refund.run_id and billing.handoff.to_agent == "agent_billing_helper"
    assert [joined.run_id for joined in continued(lane)] == [refund.run_id]


def test_two_customers_chatting_at_once_never_share_a_run(shop):
    lane, inbox = shop
    amara = start(lane, k3(says(lane, inbox, REFUND_ASK)))
    ben = start(lane, k3(says(lane, inbox, REFUND_ASK, **BEN)))
    start(lane, k3(says(lane, inbox, CONFIRM, **BEN)))
    assert ben.run_id != amara.run_id and ben.handoff.customer_ref == "cust-ben"
    [joined] = continued(lane)
    assert joined.run_id == ben.run_id and len(joined.transcript_signal_ids) == 2  # Ben's chat only, never Amara's


# --- The whole conversation, through the seam log

def test_the_seam_log_shows_every_visit_in_order(shop, tmp_path, monkeypatch):
    lane, inbox = shop
    monkeypatch.setattr(observe, "SEAM_LOG_DIR", str(tmp_path))
    first = start(lane, k3(says(lane, inbox, REFUND_ASK)))
    start(lane, k3(says(lane, inbox, CONFIRM)))
    close_run(lane, first.run_id, "resolved")
    start(lane, k3(says(lane, inbox, ANOTHER_ASK)))
    lines = [json.loads(line) for line in (tmp_path / "S4.jsonl").read_text().splitlines()]
    assert [line["out"]["request_text"] for line in lines] == [REFUND_ASK, CONFIRM, ANOTHER_ASK]
    assert ["handoff" in line["out"] for line in lines] == [True, False, True]  # visit 2 joins, so no handoff


# --- Rules that always hold, over many random conversations

@pytest.mark.parametrize("seed", range(30))
def test_rules_hold_for_any_conversation(shop, seed):
    lane, inbox = shop
    picker = random.Random(seed)
    seen, closed = [], set()
    for _ in range(picker.randint(2, 8)):
        seen.append(says(lane, inbox, picker.choice([REFUND_ASK, CONFIRM, ANOTHER_ASK, "ok"])))
        start(lane, k3(seen[-1]))
        assert len({run["run_id"] for run in published(lane, "runs.started")} - closed) == 1  # one chat, one agent: one open run
        if picker.random() < 0.3:  # S10 closes the latest run now and then
            closed.add(published(lane, "runs.started")[-1]["run_id"])
            close_run(lane, published(lane, "runs.started")[-1]["run_id"], picker.choice(["resolved", "escalated"]))
    runs, joins = [RunStarted.model_validate(p) for p in published(lane, "runs.started")], continued(lane)
    # Every visit is handled exactly once, by a new run or by joining one; joins point at a run on this chat
    assert sorted([run.task_id for run in runs] + [join.task_id for join in joins]) == sorted(f"task_{s}" for s in seen)
    assert {join.run_id for join in joins} <= {run.run_id for run in runs}
    # Each transcript is the chat up to that visit, so it never loses an earlier message
    assert all(item.transcript_signal_ids == seen[: seen.index(item.signal_id) + 1] for item in joins)
    assert all(run.handoff.transcript_signal_ids == seen[: seen.index(run.signal_id) + 1] for run in runs)
