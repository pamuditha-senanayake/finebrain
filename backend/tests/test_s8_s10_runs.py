# test_s8_s10_runs.py: S8 and S10 for the refund BDD. A run that asks the customer waits for them (S10 records it as
# awaiting_customer, the console shows it running), goes on when they answer, and is abandoned if they never do. A refund
# a person must approve waits for them. S10 records the outcome, who let the action through, and the whole chat.
# Lines: "the refund is saved with order, amount, status, and approver 'auto by policy'", "the chat is marked resolved and
# saved with its full transcript". Uses: orchestrate.py, run_resume.py, run_finish.py, tests/s7_world.py, tests/s6_world.py.
import json
import threading
from datetime import timedelta

from app.api.views import RUN_STATUS
from app.pipeline import orchestrate
from app.pipeline.contracts_run import Decision
from tests.s5_world import needs_postgres
from tests.s6_world import ask, refund, scripted
from tests.s7_world import actions, full_lane, last_record, runs, says
from tests.test_s1_refund_chat import FIRST, SECOND
from tests.test_s4_repeat_visits import LockedKeys

pytestmark = needs_postgres

# Config
DEE = {"email": "dee@example.lk", "session": "chat_sess_dee", "name": "Dee"}
DESK = {"payment_ref": "pay_FB_20260820_0311", "amount": {"amount_minor": 9500000, "currency": "LKR"}, "citations": ["order:ORD-3001", "item_policy_window"]}


def anna_asks(lane):
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)


# --- BDD: visit 1 waits, visit 2 refunds, S10 records it all

def test_visit_1_waits_for_the_customer_and_the_console_shows_it_running():
    lane = full_lane()
    anna_asks(lane)
    record = last_record(lane)
    assert record["outcome"] == "awaiting_customer" and RUN_STATUS[record["outcome"]] == "running"
    assert actions(lane) == [("tool_reply_email", "succeeded")] and lane.records.load("run_waiting", record["run_id"])


def test_visit_2_refunds_and_s10_saves_amount_status_approver_and_the_whole_chat():
    lane = full_lane()
    anna_asks(lane)
    says(lane, SECOND)
    record = last_record(lane)
    assert runs(lane)[record["run_id"]] == ["awaiting_customer", "resolved"]  # one run, two turns
    assert (record["outcome"], record["decided_by"]) == ("resolved", "auto by policy")
    refund_result = lane.bus.topics["actions.executed"][-1].payload
    assert (refund_result["tool_id"], refund_result["status"]) == ("tool_payment_refund", "succeeded")
    trace = json.loads(lane.object_store[record["trace_object_uri"]])
    assert trace["chat"] == ["msg:sig_0001", "msg:sig_0002"] and [t["action_type"] for t in trace["turns"]] == ["reply_customer", "issue_refund"]
    assert trace["action"]["arguments"]["payment_ref"] == "pay_FB_20260930_0144" and trace["action"]["money"]["amount_minor"] == 400000


def test_each_turn_has_its_own_idempotency_key_so_the_refund_is_not_mistaken_for_the_reply():
    lane = full_lane()
    anna_asks(lane)
    says(lane, SECOND)
    keys = [e.payload["idempotency_key"] for e in lane.bus.topics["actions.executed"]]
    assert keys == ["finebase_labs:run_0001:step_04", "finebase_labs:run_0001:step_04.2"]


# --- S8: waiting ends, people decide

def test_no_answer_in_48_hours_abandons_the_run_and_a_new_message_starts_fresh():
    lane = full_lane()
    anna_asks(lane)
    first = last_record(lane)["run_id"]
    orchestrate.sweep_expired(lane, lane.now + timedelta(hours=49))
    assert runs(lane)[first] == ["awaiting_customer", "abandoned"]
    lane.model, _ = scripted(ask())
    says(lane, {"id": "msg_later", "text": "I want a refund for my last order"})
    assert last_record(lane)["run_id"] != first  # a new run, not the abandoned one


def test_two_answers_at_once_take_one_turn():
    lane = full_lane()
    lane.seen_keys = LockedKeys()
    anna_asks(lane)
    lane.bus.subscribers.pop("tasks.created")  # the test hands both answers to two workers at once
    says(lane, SECOND)
    says(lane, {"id": "chat_msg_anna_3", "text": "yes please"})
    envelopes = lane.bus.topics["tasks.created"][-2:]
    workers = [threading.Thread(target=orchestrate.on_task, args=(lane, envelope)) for envelope in envelopes]
    [worker.start() for worker in workers]
    [worker.join() for worker in workers]
    assert actions(lane).count(("tool_payment_refund", "succeeded")) == 1  # never two refunds for two quick answers


def test_a_refund_a_person_must_approve_waits_for_them_then_s10_names_them():
    lane = full_lane()
    lane.model, _ = scripted(ask(citations=["order:ORD-3001"]), refund(**DESK))
    says(lane, {"id": "msg_dee_1", "text": "I want a refund for my standing desk"}, **DEE)
    says(lane, {"id": "msg_dee_2", "text": "yes, that one"}, **DEE)
    approval = lane.bus.topics["approvals.requested"][-1].payload
    assert last_record(lane)["outcome"] == "awaiting_approval" and approval["dri_id"] == "head_of_cs"
    orchestrate.decide(lane, Decision(approval_id=approval["approval_id"], decision="approve", decided_by=["head_of_cs"], decided_at=lane.now))
    lane.bus.drain()
    assert (last_record(lane)["outcome"], last_record(lane)["decided_by"]) == ("resolved", "head_of_cs")
    assert actions(lane)[-1] == ("tool_payment_refund", "succeeded")


def test_a_rejected_refund_pays_nothing():
    lane = full_lane()
    lane.model, _ = scripted(ask(citations=["order:ORD-3001"]), refund(**DESK))
    says(lane, {"id": "msg_dee_1", "text": "I want a refund for my standing desk"}, **DEE)
    says(lane, {"id": "msg_dee_2", "text": "yes, that one"}, **DEE)
    approval = lane.bus.topics["approvals.requested"][-1].payload
    orchestrate.decide(lane, Decision(approval_id=approval["approval_id"], decision="reject", decided_by=["head_of_cs"], decided_at=lane.now, comment="Past the window."))
    lane.bus.drain()
    assert ("tool_payment_refund", "succeeded") not in actions(lane) and last_record(lane)["outcome"] != "resolved"
