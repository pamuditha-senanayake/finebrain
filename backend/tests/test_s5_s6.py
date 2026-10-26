# test_s5_s6.py: S6 asks S5, and S5's bundle is what S6 reasons on. With a stand-in model, the request S6 sends must
# carry Anna's order and the policy; with real Claude, the refund it proposes must be her latest order, in full, citing them.
# Uses: stages_reason.py (S6), retrieve_case.py (S5), llm.py, fakes.py, tests/s5_world.py, scripts/test_keys.py.
import json
import os

import pytest

from app.pipeline import fakes, llm, stages_reason
from app.pipeline.contracts_signal import TaskRequest
from scripts.test_keys import ENV_PATH, load_env_file
from tests.s5_world import ask, make_lane, needs_postgres, query_for, visitor_says
from tests.test_s1_refund_chat import FIRST

pytestmark = needs_postgres

# Config
MOUSE = {"payment_ref": "pay_FB_20260930_0144", "amount": {"amount_minor": 400000, "currency": "LKR"}}


def propose(lane, task: dict, bundle, call):
    """S6 as the run calls it: the pinned skill, the masked request and S5's bundle."""
    skill = lane.graph.at_version("skill", task["skill_ref"]["id"], task["skill_ref"]["version"])
    request = lane.signals[task["signal_ids"][0]].text_masked
    return stages_reason.propose(TaskRequest.model_validate(task), bundle, request, skill, call, "run_s6_test", "step_04", lane.seed["cluster_id"], today="10 October 2026")


@pytest.fixture
def anna():
    lane = make_lane()
    task = visitor_says(lane, FIRST)
    bundle, _ = ask(lane, query_for(lane, task))
    return lane, task, bundle


def test_s6_receives_the_order_and_the_policy_from_s5(anna):
    lane, task, bundle = anna
    answer = {"tool": "issue_refund", "tool_input": {**MOUSE, "reason_code": "within_window_full", "rationale_summary": "Paid 10 days ago, inside 30 days and under LKR 50,000; never refunded.",
                                                    "citations": ["order:ORD-1002", "item_policy_window", "item_policy_auto_limit"], "confidence": 0.9}}
    call, seen = fakes.make_recorded_caller({MOUSE["payment_ref"]: answer})  # answers only if the order's payment is in S6's request
    action = propose(lane, task, bundle, call)
    request = json.dumps(seen[0]["messages"])
    assert '<document id=\\"order:ORD-1002\\" kind=\\"fact\\"' in request and "within 30 days" in request
    assert (action.action_type, action.arguments["payment_ref"], action.money.amount_minor) == ("issue_refund", MOUSE["payment_ref"], 400000)


def test_s6_cannot_cite_what_s5_did_not_give(anna):
    lane, task, bundle = anna
    answer = {"tool": "issue_refund", "tool_input": {**MOUSE, "reason_code": "within_window_full", "rationale_summary": "x",
                                                    "citations": ["order:ORD-2001"], "confidence": 0.9}}  # Ben's order: not in Anna's bundle
    call, _ = fakes.make_recorded_caller({MOUSE["payment_ref"]: answer})
    assert propose(lane, task, bundle, call).action_type == "escalate"  # feedback twice, then a person takes over


def test_without_the_order_s6_has_nothing_to_refund(anna):
    lane, task, _ = anna
    lane.vault.clear()  # the order lookup has no email to go on
    bundle, _ = ask(lane, query_for(lane, task))
    call, _ = fakes.make_recorded_caller({MOUSE["payment_ref"]: {"tool": "issue_refund", "tool_input": {}}})
    assert propose(lane, task, bundle, call).action_type == "escalate"  # no payment in the request, so no refund is invented


def test_real_claude_refunds_annas_latest_order_in_full(anna):
    load_env_file(ENV_PATH)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY in backend/.env")
    lane, task, bundle = anna
    action = propose(lane, task, bundle, llm.make_tool_caller())
    assert action.action_type == "issue_refund", action.rationale_summary
    assert (action.arguments["payment_ref"], action.money.amount_minor, action.money.currency) == (MOUSE["payment_ref"], 400000, "LKR")
    assert "order:ORD-1002" in action.citations and set(action.citations) <= {item.item_id for item in bundle.items}
