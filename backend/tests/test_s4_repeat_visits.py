# test_s4_repeat_visits.py: S4 when one chat reaches it more than once, as in the full refund BDD. Real S1, S2, S3; S4 by hand.
# Visit 1: "I want a refund for my last order" starts the run and hands the chat to the Refund agent.
# Visit 2: "yes, that one" matches no rule, so S3 hands it on for the open run; S4 joins it: inbox, runs.continued, no new run.
# Visit 3: a message after the run closed starts a fresh run. Other chats never share a run; two workers never start two.
# Uses: stages_orchestrate.py, stages_orchestrate_chat.py, stages_record.py, tests/test_s4_orchestrate_bdd.py, tests/test_s1_refund_chat.py.
import json
import random
import threading

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, observe, stages_record
from app.pipeline import stages_orchestrate_chat as chat
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.contracts_start import RunStarted
from tests.golden import NOW, SEED
from tests.test_s1_refund_chat import CHAT, CONVERSATION, FIRST, SECOND, SESSION
from tests.test_s4_orchestrate_bdd import lane as s4_lane
from tests.test_s4_orchestrate_bdd import published, start, tasks

# Config
lane = s4_lane  # the S4 lane fixture: real S1 to S3, S4 handed each task by the test
AGAIN = {"id": "chat_msg_anna_3", "text": "I want a refund for another order too"}
BILLING = {"id": "chat_msg_anna_b", "text": "Also a billing question: why was I charged twice on my invoice?"}


def post(lane, message: dict, session: str = SESSION, email: str = "anna@example.lk") -> None:
    """One chat message through the webhook, from any visitor, then S1, S2 and S3 catch up."""
    body = json.dumps({"visitor_name": "Visitor", "visitor_email": email, "text": message["text"], "sent_at": "2026-10-10T09:55:00+05:30"}).encode()
    headers = {"content-type": "application/json", "x-external-id": message["id"], "session": session,
               "x-signature": capture_api.sign(SEED["connectors"][CHAT]["secret"], body)}
    assert TestClient(capture_api.create_app(lane)).post(f"/capture/{CHAT}", content=body, headers=headers).status_code == 202
    lane.bus.drain()


def latest_task(lane):
    return tasks(lane)[-1]


def close_run(lane, run_id: str, outcome: str) -> None:
    """S10 closes (or pauses) the run, as the recorder saves it from runs.completed."""
    task_id = next(run["task_id"] for run in published(lane, "runs.started") if run["run_id"] == run_id)
    task = TaskRequest.model_validate(next(t.payload for t in tasks(lane) if t.payload["task_id"] == task_id))
    record, _ = stages_record.record(task, None, [], outcome, None, lane.seed, NOW, NOW, run_id=run_id)
    lane.records.save("run", run_id, record)


# --- Visit 2 joins the open run

def test_visit_2_the_confirmation_joins_the_open_refund_run(lane):
    post(lane, FIRST)
    first = start(lane, latest_task(lane))
    post(lane, SECOND)
    follow_up = latest_task(lane)
    assert chat.CONTINUES_FLAG in follow_up.payload["flags"]  # S3 matched no rule but found the chat's open run
    assert start(lane, follow_up) is None  # no new run for S5 to S10
    [joined] = chat.inbox(lane, first.run_id)
    assert (joined.request_text, joined.transcript_signal_ids) == (SECOND["text"], ["sig_0001", "sig_0002"])
    assert published(lane, "runs.continued")[0]["run_id"] == first.run_id and len(published(lane, "runs.started")) == 1


def test_visit_2_while_the_run_waits_for_approval_still_joins_it(lane):
    post(lane, FIRST)
    first = start(lane, latest_task(lane))
    close_run(lane, first.run_id, "awaiting_approval")
    post(lane, SECOND)
    start(lane, latest_task(lane))
    assert [message.signal_id for message in chat.inbox(lane, first.run_id)] == ["sig_0002"]


def test_the_same_visit_delivered_twice_joins_once(lane):
    post(lane, FIRST)
    first = start(lane, latest_task(lane))
    post(lane, SECOND)
    start(lane, latest_task(lane))
    start(lane, latest_task(lane))
    assert len(chat.inbox(lane, first.run_id)) == 1 and len(published(lane, "runs.continued")) == 1


# --- Visit 3 after the run closed starts fresh

@pytest.mark.parametrize("outcome", ["resolved", "escalated", "failed", "blocked", "abandoned"])
def test_visit_3_after_the_run_closed_starts_a_fresh_run(lane, outcome):
    post(lane, FIRST)
    first = start(lane, latest_task(lane))
    post(lane, SECOND)
    start(lane, latest_task(lane))
    close_run(lane, first.run_id, outcome)
    post(lane, AGAIN)
    second = start(lane, latest_task(lane))
    assert second.run_id != first.run_id and second.recipe.skill_ref.id == "skill_refund_handling"
    assert second.handoff.transcript_signal_ids == ["sig_0001", "sig_0002", "sig_0003"]  # the new run still sees the whole chat


def test_a_thank_you_after_the_run_closed_is_not_forced_into_a_run(lane):
    post(lane, FIRST)
    close_run(lane, start(lane, latest_task(lane)).run_id, "resolved")
    post(lane, {"id": "chat_msg_anna_t", "text": "thanks!"})
    assert len(tasks(lane)) == 1 and published(lane, "tasks.unrouted")[-1]["text_masked"] == "thanks!"


# --- Other agents and other chats never share a run

def test_a_billing_question_mid_refund_gets_its_own_run_and_a_reply_joins_the_newest(lane):
    post(lane, FIRST)
    refund = start(lane, latest_task(lane))
    post(lane, BILLING)
    billing = start(lane, latest_task(lane))
    post(lane, SECOND)
    start(lane, latest_task(lane))
    assert billing.run_id != refund.run_id and billing.handoff.to_agent == "agent_billing_helper"
    assert published(lane, "runs.continued")[0]["run_id"] == billing.run_id  # an unmatched reply goes to the chat's newest open run


def test_two_customers_chatting_at_once_never_share_a_run(lane):
    post(lane, FIRST)
    anna = start(lane, latest_task(lane))
    post(lane, {"id": "chat_msg_ben_1", "text": FIRST["text"]}, session="chat_sess_ben", email="ben@example.lk")
    ben = start(lane, latest_task(lane))
    post(lane, {"id": "chat_msg_ben_2", "text": SECOND["text"]}, session="chat_sess_ben", email="ben@example.lk")
    start(lane, latest_task(lane))
    assert ben.run_id != anna.run_id and ben.handoff.customer_ref != anna.handoff.customer_ref
    [joined] = chat.inbox(lane, ben.run_id)
    assert joined.transcript_signal_ids == ["sig_0002", "sig_0003"] and chat.inbox(lane, anna.run_id) == []


# --- Two workers on one chat at the same moment

class LockedKeys(set):
    """A key set whose claim is atomic across threads, as Valkey SET NX is across workers."""
    lock = threading.Lock()

    def claim(self, key: str) -> bool:
        with self.lock:
            return not (key in self or self.add(key))


def test_two_workers_starting_one_chat_at_once_make_one_run(lane):
    lane.seen_keys = LockedKeys()
    post(lane, FIRST)
    post(lane, {"id": "chat_msg_anna_r", "text": "please refund my last order"})  # a second refund ask, routed on its own
    first, second = tasks(lane)[-2:]
    workers = [threading.Thread(target=start, args=(lane, envelope)) for envelope in (first, second)]
    [worker.start() for worker in workers]
    [worker.join() for worker in workers]
    assert len(published(lane, "runs.started")) == 1 and len(published(lane, "runs.continued")) == 1


def test_a_worker_that_lost_the_claim_and_sees_no_run_retries_later(lane, monkeypatch):
    monkeypatch.setattr(chat, "WAIT_DELAY", 0)
    post(lane, FIRST)
    lane.seen_keys.add(f"{SEED['tenant_id']}:s4:start:{CONVERSATION}:agent_refund_worker:0")  # another worker holds the claim
    with pytest.raises(chat.ConversationBusy):
        start(lane, latest_task(lane))
    lane.seen_keys.discard(f"{SEED['tenant_id']}:s4:start:{CONVERSATION}:agent_refund_worker:0")  # it crashed and let go
    assert start(lane, latest_task(lane)).run_id  # the bus delivers the task again, and it starts


# --- The whole conversation, through the seam log

def test_the_seam_log_shows_every_visit_in_order(lane, tmp_path, monkeypatch):
    monkeypatch.setattr(observe, "SEAM_LOG_DIR", str(tmp_path))
    post(lane, FIRST)
    first = start(lane, latest_task(lane))
    post(lane, SECOND)
    start(lane, latest_task(lane))
    close_run(lane, first.run_id, "resolved")
    post(lane, AGAIN)
    start(lane, latest_task(lane))
    lines = [json.loads(line) for line in (tmp_path / "S4.jsonl").read_text().splitlines()]
    assert [line["out"]["request_text"] for line in lines] == [FIRST["text"], SECOND["text"], AGAIN["text"]]
    assert ["handoff" in line["out"] for line in lines] == [True, False, True]  # visit 2 joins, so no hand-off


# --- Rules that always hold, over many random conversations

@pytest.mark.parametrize("seed", range(30))
def test_rules_hold_for_any_conversation(lane, seed):
    picker = random.Random(seed)
    handled, closed = 0, set()
    for turn in range(picker.randint(2, 8)):
        post(lane, {"id": f"m{seed}_{turn}", "text": picker.choice([FIRST["text"], SECOND["text"], AGAIN["text"], BILLING["text"], "ok"])})
        for envelope in tasks(lane)[handled:]:
            start(lane, envelope)
        handled = len(tasks(lane))
        open_agents = [run["agent_id"] for run in published(lane, "runs.started") if run["run_id"] not in closed]
        assert len(open_agents) == len(set(open_agents))  # one chat: never two open runs for one agent
        if picker.random() < 0.3 and published(lane, "runs.started"):  # S10 closes the latest run now and then
            closed.add(published(lane, "runs.started")[-1]["run_id"])
            close_run(lane, published(lane, "runs.started")[-1]["run_id"], picker.choice(["resolved", "escalated"]))
    runs, joins = [RunStarted.model_validate(p) for p in published(lane, "runs.started")], published(lane, "runs.continued")
    order = [s["signal_id"] for s in lane.records.history(chat.MESSAGES_KIND, CONVERSATION)]
    # Every task is handled exactly once, by a new run or by joining one, and joins only point at runs that exist
    assert sorted([run.task_id for run in runs] + [join["task_id"] for join in joins]) == sorted({t.payload["task_id"] for t in tasks(lane)})
    assert {join["run_id"] for join in joins} <= {run.run_id for run in runs}
    # Each hand-off carries the chat up to that message, so no earlier message is ever lost
    assert all(run.handoff.transcript_signal_ids == order[: order.index(run.signal_id) + 1] for run in runs)
