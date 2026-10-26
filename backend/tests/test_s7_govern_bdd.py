# test_s7_govern_bdd.py: S7 Govern for the refund BDD, after the real S1 to S6. S7 reads the payment from the shop's own
# database at decision time, only when it is the case customer's, plus the refunds already made. Lines: "the Refund agent
# checks the policy", "the order is inside 30 days, under the limit, and not refunded before". Then the cases that must
# go to a person or stop. Uses: stages_govern.py, govern_payments.py, run_steps.py, tests/s7_world.py, tests/s6_world.py.
import psycopg

from app.pipeline import govern_payments, run_steps, stages_orchestrate, stages_reason
from app.pipeline.contracts_reason import ContextBundle
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.tools import TOOLS
from scripts import shop_db
from tests.s5_world import connect_shop, needs_postgres
from tests.s6_world import ask, refund, scripted
from tests.s7_world import actions, full_lane, last_record, runs, says, verdicts
from tests.test_s1_refund_chat import FIRST, SECOND

pytestmark = needs_postgres

# Config
DEE = {"email": "dee@example.lk", "session": "chat_sess_dee", "name": "Dee"}
DESK = {"payment_ref": "pay_FB_20260820_0311", "amount": {"amount_minor": 9500000, "currency": "LKR"}, "citations": ["order:ORD-3001", "item_policy_window"]}


def rules(verdict: dict) -> dict[str, bool]:
    return {result["rule_id"]: result["passed"] for result in verdict["policy_results"]}


# --- BDD: S7 checks the policy on the real order

def test_annas_mouse_passes_every_rule_and_runs_on_its_own():
    lane = full_lane()
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    says(lane, SECOND)
    verdict = verdicts(lane)[-1]
    assert rules(verdict) == {"refund.not_refunded_before": True, "refund.window": True, "refund.auto_limit": True}
    assert (verdict["route"], verdict["criticality"]) == ("execute", 0)
    assert [r["explanation"] for r in verdict["policy_results"]] == ["LKR 0 refunded before", "9 days since purchase, window is 30", "LKR 4,000 against a limit of LKR 50,000"]
    assert actions(lane)[-1] == ("tool_payment_refund", "succeeded")


# --- The cases a person must decide

def test_an_order_refunded_in_part_before_needs_a_person():
    lane = full_lane()
    with psycopg.connect(shop_db.owner_url(), autocommit=True) as shop:
        shop.execute("INSERT INTO shop.refunds VALUES ('RF-0010', 'ORD-1002', 50000, 'approved', '2026-10-05T10:00:00+05:30')")
    lane.model, _ = scripted(ask(), refund(amount={"amount_minor": 350000, "currency": "LKR"}))
    says(lane, FIRST)
    says(lane, SECOND)
    verdict = verdicts(lane)[-1]
    assert rules(verdict)["refund.not_refunded_before"] is False and verdict["route"] == "approval_required" and verdict["criticality"] == 3
    assert last_record(lane)["outcome"] == "awaiting_approval" and ("tool_payment_refund", "succeeded") not in actions(lane)


def test_a_large_late_order_needs_a_person():
    lane = full_lane()
    lane.model, _ = scripted(ask(citations=["order:ORD-3001"]), refund(**DESK))
    says(lane, {"id": "msg_dee_1", "text": "I want a refund for my standing desk"}, **DEE)
    says(lane, {"id": "msg_dee_2", "text": "yes, that one"}, **DEE)
    verdict = verdicts(lane)[-1]
    assert rules(verdict) == {"refund.not_refunded_before": True, "refund.window": False, "refund.auto_limit": False}
    assert verdict["route"] == "approval_required" and verdict["required_approvers"]["roles"] == ["head_of_cs"]


def test_a_second_run_for_a_refunded_order_never_refunds_on_its_own():
    lane = full_lane()
    lane.model, _ = scripted(ask(), refund(), ask(), refund())
    says(lane, FIRST)
    says(lane, SECOND)  # refunded, run resolved; the shop has not recorded it yet, the brain has
    says(lane, {"id": "msg_again_1", "text": "I want a refund for my last order"}, session="chat_sess_anna_2")
    says(lane, {"id": "msg_again_2", "text": "yes, that one"}, session="chat_sess_anna_2")
    signal = lane.signals[lane.bus.topics["tasks.created"][-1].payload["signal_ids"][0]]
    seen = govern_payments.payments_for(lane, signal, "pay_FB_20260930_0144")["pay_FB_20260930_0144"]
    assert (seen["amount_minor"], seen["refunded_minor"]) == (400000, 400000)  # the brain's own refund counts, before the shop knows it
    assert last_record(lane)["outcome"] == "escalated" and actions(lane).count(("tool_payment_refund", "succeeded")) == 1  # nothing left: a person looks


# --- S7 checks again, in code, whatever S6 let through

def test_another_customers_payment_is_never_checked_as_this_customers():
    lane = full_lane()
    lane.model, _ = scripted(ask())
    says(lane, FIRST)
    task = TaskRequest.model_validate(lane.bus.topics["tasks.created"][0].payload)
    bens = refund(payment_ref="pay_FB_20261005_0207")["tool_input"]  # Ben's lamp, as if S6 had been fooled into it
    action = stages_reason.build_action("issue_refund", TOOLS["issue_refund"]["args"].model_validate(bens), stages_reason.usage_of([], "m"), "run_x", "step_04", "cc")
    empty = ContextBundle(items=[], denied_count=0, denied_reasons=[], access_decision_ids=[], latency_ms=0)
    _, verdict = run_steps.govern_once(lane, task, action, empty, stages_orchestrate.principal_of(lane, task.agent_id), lane.bus.topics["tasks.created"][0], "")
    assert verdict.route == "escalate" and verdict.policy_results == []  # S7 found no payment of Anna's by that ref


def test_the_shop_down_when_s7_checks_means_a_person_looks():
    lane = full_lane()
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    connect_shop(lane, url=shop_db.reader_url().replace(":5433/", ":5999/"))  # down after S5 read it, before S7 checks
    says(lane, SECOND)
    assert verdicts(lane)[-1]["route"] == "escalate" and ("tool_payment_refund", "succeeded") not in actions(lane)
    assert runs(lane)[last_record(lane)["run_id"]][-1] == "escalated"
