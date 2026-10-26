# test_act.py: S9 step 7 (runners per tool, rate limits, stored results, stale policy) and step 8 (retryable errors
# on the same key, non-retryable failure tells a human, crash after paying never pays twice).
# Uses: stages_act.py, tool_runners.py, orchestrate.py, store_valkey.py, tests/golden.py.
import uuid

import pytest

from app.pipeline import fakes, observe, orchestrate, stages_act
from app.pipeline.contracts_reason import ProposedAction
from app.pipeline.contracts_run import Decision, GovernanceVerdict
from app.pipeline.store_valkey import connect, valkey_is_up
from app.pipeline.tool_runners import MemoryRateLimiter, MemoryResults, ValkeyRateLimiter, ValkeyResults
from app.pipeline.tools import TOOLS
from tests.golden import NOW, RAW, SEED, golden, recorded_answers

# Config
REFUND = ProposedAction.model_validate(golden("s2", "ProposedAction"))
EXECUTE = GovernanceVerdict.model_validate(golden("s2", "GovernanceVerdict"))


# --- Helpers

def tooling(gateway=None, sender=None, sleeps=None) -> dict:
    return {
        "limiter": MemoryRateLimiter(), "results": MemoryResults(),
        "sleep": (sleeps.append if sleeps is not None else lambda seconds: None),
        "runners": {"shop_database": gateway or fakes.make_fake_gateway()[0], "chat": sender or fakes.make_fake_sender()[0]},
    }


def act(action=REFUND, tools=None, run_id=None):
    action = action.model_copy(update={"run_id": run_id}) if run_id else action
    return stages_act.act(action, EXECUTE, None, SEED["tenant_id"], tools or tooling(), fakes.make_id_maker(), NOW)


def counting(gateway):
    calls = []
    return (lambda *args: calls.append(1) or gateway(*args)), calls


# --- Step 7: runners

def test_each_tool_goes_to_its_runner():
    sender, sent = fakes.make_fake_sender()
    gateway, paid = fakes.make_fake_gateway()
    tools = tooling(gateway, sender)
    reply = REFUND.model_copy(update={"action_type": "reply_customer", "tool_id": "tool_reply_email", "arguments": {"message_plain": "Your refund is on its way."}, "money": None})
    escalate = REFUND.model_copy(update={"action_type": "escalate", "tool_id": "tool_escalate", "arguments": {"reason": "unclear"}, "money": None})
    results = [act(REFUND, tools, "run_a"), act(reply, tools, "run_b"), act(escalate, tools, "run_c")]
    assert [result.status for result in results] == ["succeeded"] * 3
    assert (len(paid), [message["message_plain"] for message in sent], results[2].response_summary) == (1, ["Your refund is on its way."], "handed to a human")


def test_rate_limit_stops_refunds_over_the_per_minute_limit(monkeypatch):
    monkeypatch.setitem(TOOLS["issue_refund"], "rate_per_minute", 2)
    tools = tooling()
    results = [act(REFUND, tools, f"run_{number}") for number in range(3)]
    assert [result.status for result in results] == ["succeeded", "succeeded", "failed"]
    assert (results[2].error.code, results[2].error.retryable) == ("RateLimited", True)


# --- Step 8: retries and failures

def test_retryable_errors_are_retried_on_the_same_key():
    gateway, calls = counting(fakes.make_fake_gateway(fail_with="gateway_timeout", failures=2)[0])
    sleeps = []
    result = act(tools=tooling(gateway, sleeps=sleeps))
    assert (result.status, len(calls), sleeps) == ("succeeded", 3, [0.2, 0.4])


def test_retryable_errors_give_up_after_six_attempts():
    gateway, calls = counting(fakes.make_fake_gateway(fail_with="gateway_timeout")[0])
    result = act(tools=tooling(gateway))
    assert (result.status, result.error.retryable, len(calls)) == ("failed", True, 6)


def test_not_retryable_fails_at_once_and_a_human_is_told():
    gateway, paid = fakes.make_fake_gateway(fail_with="card_closed", retryable=False)
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], gateway, NOW)
    orchestrate.capture_signal(lane, RAW["s2_refund_monthly_in_policy"])
    lane.bus.drain()
    result = lane.bus.topics["actions.executed"][-1].payload
    assert (result["status"], result["error"]["code"], "compensation: none defined" in result["response_summary"]) == ("failed", "card_closed", True)
    assert lane.bus.topics["ui.events"][-1].payload["display"]["status"] == "failed"


def test_a_retry_after_a_crash_never_pays_twice():
    observe.reset_counts()
    gateway, paid = fakes.make_fake_gateway()
    gateway, calls = counting(gateway)
    tools = tooling(gateway)
    first, again = act(tools=tools), act(tools=tools)  # the worker crashed after paying and ran the step again
    assert (first.external_ref == again.external_ref, len(calls), len(paid)) == (True, 1, 1)
    assert observe.read_count("s9.replayed") == 1


# --- Stale policy before acting on an approval

def stale_policy_lane(escalation_criticality: int):
    gateway, paid = fakes.make_fake_gateway()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], gateway, NOW)
    orchestrate.capture_signal(lane, RAW["s3_refund_annual_late_large"])
    lane.bus.drain()
    policy = {**SEED["refund_policy"], "escalation": {"criticality": escalation_criticality, "approvers": {"tier": "L1", "count": 2, "roles": ["dri", "leader"]}}}
    lane.graph.put("policy", "policy_refund", 4, "cmt_0009", policy)  # released while the approval waited
    approval_id = lane.bus.topics["approvals.requested"][-1].payload["approval_id"]
    orchestrate.decide(lane, Decision(approval_id=approval_id, decision="approve", decided_by=["head_of_cs"], decided_at=NOW))
    lane.bus.drain()
    return lane, paid


def test_newer_policy_that_is_no_stricter_still_pays():
    observe.reset_counts()
    lane, paid = stale_policy_lane(escalation_criticality=3)
    assert len(paid) == 1 and observe.read_count("s9.policy_changed") == 1


def test_newer_stricter_policy_opens_a_new_approval_instead_of_paying():
    lane, paid = stale_policy_lane(escalation_criticality=4)
    assert paid == {} and len(lane.bus.topics["approvals.requested"]) == 2
    assert lane.bus.topics["approvals.requested"][-1].payload["criticality"] == 4


# --- Valkey versions

@pytest.mark.skipif(not valkey_is_up(), reason="no Valkey on localhost:6379")
def test_valkey_limiter_and_results():
    client, tenant = connect(), f"test_{uuid.uuid4().hex[:8]}"
    limiter = ValkeyRateLimiter(client)
    assert [limiter.allow(tenant, "tool_x", 2, NOW) for _ in range(3)] == [True, True, False]
    results = ValkeyResults(client, f"{tenant}:results")
    results.put("key_1", {"status": "succeeded"})
    results.put("key_1", {"status": "overwritten?"})
    assert results.get("key_1") == {"status": "succeeded"} and results.get("key_2") is None


@pytest.mark.parametrize("stamp", ["2026-10-26T12:08:55.33838+00:00", "2026-10-26T12:08:55.338+00:00", "2026-10-26T12:08:55Z", "2026-10-26T12:08:55.1234567+00:00"])
def test_a_chats_timestamp_reads_whatever_its_fraction_digits(stamp):
    from app.pipeline.tools_chat import read_time  # the portal drops trailing zeros, which Python 3.10 cannot read alone
    assert read_time(stamp).replace(microsecond=0).isoformat() == "2026-10-26T12:08:55+00:00"
