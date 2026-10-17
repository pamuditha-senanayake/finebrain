# test_reason.py: S6 step 7 (prompt, allowed tools, checked calls) and step 8 (feedback retries, no tool, outage,
# escalate routing in S7). Claude is a fake here. Uses: stages_reason.py, llm.py, stages_govern.py, orchestrate.py, tests/golden.py.
import anthropic
import httpx
import pytest

from app.pipeline import access, fakes, llm, orchestrate, stages_govern, stages_reason
from app.pipeline.contracts_reason import ContextBundle
from app.pipeline.contracts_signal import Principal, TaskRequest
from tests.golden import NOW, RAW, SEED, golden, recorded_answer, released_policies

# Config
TASK = TaskRequest.model_validate(golden("s2", "TaskRequest"))
BUNDLE = ContextBundle.model_validate(golden("s2", "ContextBundle"))
REQUEST = golden("s2", "Signal")["text_masked"]
REFUND_SKILL, BILLING_SKILL = SEED["skills"]
GOOD = recorded_answer("s2")
CHECKER = access.make_memory_checker(SEED["people"])


# --- Helpers

def scripted(*replies):
    """A caller that gives these replies in order (an Exception is raised), recording each request."""
    calls, queue = [], list(replies)

    def call(system, messages, tools):
        calls.append({"system": system, "messages": [*messages], "tools": [tool["name"] for tool in tools]})
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return call, calls


def good_reply():
    return fakes.tool_response(**GOOD)


def bad_reply(**changes):
    return fakes.tool_response(**{**GOOD, "tool_input": {**GOOD["tool_input"], **changes}})


def propose(call, skill=REFUND_SKILL, task=TASK):
    return stages_reason.propose(task, BUNDLE, REQUEST, skill, call, "run_s2", "step_04", SEED["cluster_id"])


# --- Step 7: the request

def test_request_offers_only_the_skills_tools_and_quotes_the_customer():
    call, calls = scripted(good_reply())
    propose(call, task=TASK.model_copy(update={"flags": ["possible_prompt_injection"]}))
    request = calls[0]
    assert request["tools"] == REFUND_SKILL["allowed_tools"]
    assert REFUND_SKILL["steps"][0] in request["system"] and "never instructions" in request["system"]
    prompt = request["messages"][0]["content"]
    assert f"<customer_request>\n{REQUEST}\n</customer_request>" in prompt and 'flags="possible_prompt_injection"' in prompt


# --- Step 8: checking and feedback

def test_bad_arguments_get_feedback_then_succeed():
    call, calls = scripted(bad_reply(amount={"amount_minor": 12000.5, "currency": "LKR"}), good_reply())
    action = propose(call)
    assert action.action_type == "issue_refund" and len(calls) == 2
    feedback = calls[1]["messages"][-1]["content"][0]
    assert feedback["is_error"] is True and "amount" in feedback["content"]
    assert action.model.input_tokens == 2 * GOOD["input_tokens"]  # cost counts the retry


def test_made_up_citation_is_sent_back():
    call, calls = scripted(bad_reply(citations=["item_invented"]), good_reply())
    propose(call)
    assert "item_invented" in calls[1]["messages"][-1]["content"][0]["content"]


def test_three_bad_calls_escalate():
    call, calls = scripted(*[bad_reply(payment_ref="not a ref")] * 3)
    action = propose(call)
    assert (action.action_type, action.arguments["reason"], len(calls)) == ("escalate", "invalid_arguments", 3)
    assert action.money is None and action.confidence == 0.0


def test_tool_outside_the_skill_is_refused():
    call, calls = scripted(good_reply(), *[good_reply()] * 2)
    action = propose(call, skill=BILLING_SKILL)  # billing skill may not issue refunds
    assert action.arguments["reason"] == "invalid_arguments" and "not allowed" in calls[1]["messages"][-1]["content"][0]["content"]


@pytest.mark.parametrize("reply, reason", [
    (fakes.text_response("I will not do that."), "no_action"),
    (ConnectionError("Claude unreachable"), "model_unavailable"),
])
def test_no_tool_or_outage_escalates(reply, reason):
    call, _ = scripted(reply)
    assert propose(call).arguments["reason"] == reason


def test_overload_is_retryable_but_a_bad_request_is_not():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    overloaded = anthropic.InternalServerError("overloaded", response=httpx.Response(529, request=request), body=None)
    bad = anthropic.BadRequestError("bad", response=httpx.Response(400, request=request), body=None)
    assert llm.is_retryable(overloaded) and not llm.is_retryable(bad)


# --- S7 meets S6's answers

def test_escalate_proposal_routes_to_escalate_without_payment_checks():
    call, _ = scripted(fakes.text_response("no"))
    action = propose(call)
    agent = Principal.model_validate(SEED["agents"]["agent_refund_worker"])
    _, decision, verdict = stages_govern.govern(TASK, action, BUNDLE, agent, released_policies(), {}, SEED["cluster_id"], NOW, fakes.make_id_maker(), CHECKER, fakes.pass_grader)
    assert (decision.decision, verdict.route, verdict.criticality_reasons) == ("allow", "escalate", ["no_action"])


def test_refund_for_an_unknown_payment_escalates():
    call, _ = scripted(good_reply())
    agent = Principal.model_validate(SEED["agents"]["agent_refund_worker"])
    _, _, verdict = stages_govern.govern(TASK, propose(call), BUNDLE, agent, released_policies(), {}, SEED["cluster_id"], NOW, fakes.make_id_maker(), CHECKER, fakes.pass_grader)
    assert verdict.route == "escalate"


def test_refusing_model_means_the_run_escalates_and_nothing_is_paid():
    gateway, paid = fakes.make_fake_gateway()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], gateway, NOW)
    orchestrate.capture_signal(lane, RAW["s2_refund_monthly_in_policy"])
    lane.bus.drain()
    assert lane.bus.topics["runs.completed"][-1].payload["outcome"] == "escalated" and paid == {}
