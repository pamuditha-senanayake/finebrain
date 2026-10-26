# s6_world.py: helpers for S6 tests. A visit runs the real S1 to S3, S4 starts or joins the run, then S5 and S6 take one
# turn (run_steps.reason_turn or continue_turn), exactly as the run does before S7. The model is a script, a stand-in or
# real Claude. Uses: run_steps.py, stages_orchestrate.py, fakes.py, llm.py, tests/s5_world.py, scripts/test_keys.py.
import os

import pytest

from app.pipeline import fakes, llm, run_steps, stages_orchestrate
from app.pipeline.contracts_signal import TaskRequest
from scripts.test_keys import ENV_PATH, load_env_file
from tests.s5_world import visitor_says
from tests.test_s1_refund_chat import FIRST, SECOND

# Config
MOUSE = {"payment_ref": "pay_FB_20260930_0144", "amount": {"amount_minor": 400000, "currency": "LKR"}}


def visit_1(lane, message: dict = FIRST, **who):
    """The first message: S4 starts the run, then S5 and S6 take its first turn. Returns (run started, bundle, action)."""
    visitor_says(lane, message, **who)
    envelope = lane.bus.topics["tasks.created"][-1]
    started = stages_orchestrate.begin_run(lane, envelope)
    bundle, action = run_steps.reason_turn(lane, TaskRequest.model_validate(envelope.payload), started.run_id, envelope)
    return started, bundle, action


def visit_2(lane, message: dict = SECOND, **who):
    """A later message: S3 hands it on for the open run, S4 joins it, then S5 and S6 take the run's next turn."""
    visitor_says(lane, message, **who)
    envelope = lane.bus.topics["tasks.created"][-1]
    assert stages_orchestrate.begin_run(lane, envelope) is None  # joined, not a second run
    joined = lane.bus.topics["runs.continued"][-1]
    bundle, action = run_steps.continue_turn(lane, joined.payload, joined)
    return joined.payload, bundle, action


def scripted(*replies):
    """A model that answers with these tool calls in order, recording each request it was sent."""
    calls, queue = [], [fakes.tool_response(**reply) for reply in replies]

    def call(system, messages, tools):
        calls.append({"system": system, "messages": [*messages]})
        return queue.pop(0) if queue else fakes.text_response("no more answers")

    return call, calls


def refund(**change) -> dict:
    """A refund of Anna's mouse, as a model would call it."""
    tool_input = {**MOUSE, "reason_code": "within_window_full", "rationale_summary": "Inside 30 days, under the limit, never refunded.",
                  "citations": ["order:ORD-1002", "item_policy_window", "item_policy_auto_limit"], "confidence": 0.9}
    return {"tool": "issue_refund", "tool_input": {**tool_input, **change}}


def ask(message: str = "Is it order ORD-1002, the wireless mouse, LKR 4,000 paid on 30 September?", citations: list[str] = ("order:ORD-1002",)) -> dict:
    """A short confirming question, as a model would call it."""
    return {"tool": "reply_customer", "tool_input": {"message_plain": message, "awaits_customer": True, "rationale_summary": "Confirm the order first.",
                                                      "citations": list(citations), "confidence": 0.9}}


def real_claude():
    """The real reasoning model, or a skip when the key is missing."""
    load_env_file(ENV_PATH)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY in backend/.env")
    return llm.make_tool_caller()
