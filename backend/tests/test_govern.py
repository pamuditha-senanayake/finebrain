# test_govern.py: S7 step 7 (OPA access, graph policies, section 2 bumps, injection rule, gates, C4 cooling) and
# step 8 (OPA unreachable, failed gate back to S6 once, grader outage, missing policy). OPA cases skip if it is down.
# Uses: stages_govern.py, access.py, llm.py, orchestrate.py, tests/golden.py.
from types import SimpleNamespace

import pytest

from app.pipeline import access, fakes, llm, orchestrate, stages_govern
from app.pipeline.contracts_reason import AccessCheck, ContextBundle, ProposedAction, Resource
from app.pipeline.contracts_signal import Principal, TaskRequest, Touches
from tests.golden import NOW, RAW, SEED, golden, recorded_answer, released_policies

# Config
AGENT = Principal.model_validate(SEED["agents"]["agent_refund_worker"])
CHECKER = access.make_memory_checker(SEED["people"])
OPA_UP = access.opa_is_up()


# --- Helpers

def govern(run_key="s2", task_changes=None, action_changes=None, policies=None, checker=CHECKER, grade=fakes.pass_grader):
    task = TaskRequest.model_validate({**golden(run_key, "TaskRequest"), **(task_changes or {})})
    action = ProposedAction.model_validate(golden(run_key, "ProposedAction")).model_copy(update=action_changes or {})
    bundle = ContextBundle.model_validate(golden(run_key, "ContextBundle"))
    _, decision, verdict = stages_govern.govern(task, action, bundle, AGENT, released_policies() if policies is None else policies, SEED["payments"], SEED["cluster_id"], NOW, fakes.make_id_maker(), checker, grade)
    return decision, verdict


def access_check(capabilities, tier="L3", sensitivity="confidential", on_behalf_of=None):
    principal = Principal(type="agent", id="agent_x", capabilities=capabilities, tier=tier)
    resource = Resource(type="payment", id="pay_x", cluster_id="customer_care", sensitivity=sensitivity)
    return AccessCheck(check_id="chk_1", principal=principal, on_behalf_of=on_behalf_of, action="refund.propose", resource=resource)


ACCESS_CASES = [
    (access_check(["refund.propose"]), "capability_and_tier"),
    (access_check(["kb.read"]), "missing_capability"),
    (access_check(["refund.propose"], sensitivity="restricted"), "sensitivity_by_tier"),
    (access_check(["refund.propose"], tier="L1", sensitivity="restricted", on_behalf_of="support_operator_1"), "on_behalf_of"),
    (access_check(["refund.propose"], on_behalf_of="someone_unknown"), "on_behalf_of"),
]


# --- Step 7: access, the same answers from Python and from OPA

@pytest.mark.parametrize("check, rule_id", ACCESS_CASES)
def test_memory_rules_answer(check, rule_id):
    assert CHECKER(check)["rule_id"] == rule_id


@pytest.mark.skipif(not OPA_UP, reason="no OPA on localhost:8181")
@pytest.mark.parametrize("check, rule_id", ACCESS_CASES)
def test_opa_gives_the_same_answer(check, rule_id):
    assert access.make_opa_checker(SEED["people"])(check)["rule_id"] == rule_id


# --- Step 7: policy, bumps, injection, gates

def test_policy_comes_from_the_graph():
    policies = released_policies()
    policies["policy_refund"] = {**policies["policy_refund"], "window_days": 60}  # a released change: 60 day window
    _, verdict = govern("s3", policies=policies)
    assert verdict.criticality_reasons == ["above_auto_threshold"]  # 41 days is now inside the window


def test_each_sensitive_touch_moves_up_one_level():
    touches = Touches(money=True, personal_data=True, public_content=True, legal_tax=False, clusters=["customer_care", "finance"])
    _, verdict = govern(action_changes={"touches": touches})
    assert (verdict.criticality, verdict.route) == (3, "approval_required")  # money waived by policy; 3 bumps
    assert verdict.criticality_reasons == ["touches_personal_data", "touches_public_content", "multiple_clusters"]


def test_flagged_case_never_runs_on_its_own():
    _, verdict = govern(task_changes={"flags": ["possible_prompt_injection"]})
    assert (verdict.criticality, verdict.route, verdict.required_approvers.roles) == (2, "approval_required", ["steward"])
    assert "possible_prompt_injection" in verdict.criticality_reasons


@pytest.mark.parametrize("changes, grade, gate", [
    ({"confidence": 0.3}, fakes.pass_grader, "confidence"),
    ({}, lambda rationale, documents, context: (False, "FAIL: limit not in documents"), "grounded"),
])
def test_failed_gate_escalates(changes, grade, gate):
    _, verdict = govern(action_changes=changes, grade=grade)
    assert verdict.route == "escalate" and [g.gate_id for g in verdict.quality_gates if not g.passed] == [gate]


def test_c4_gets_a_cooling_period():
    touches = Touches(money=True, personal_data=True, public_content=True, legal_tax=True, clusters=["customer_care"])
    _, verdict = govern(task_changes={"base_criticality": 1}, action_changes={"touches": touches})
    assert (verdict.criticality, verdict.cooling_period_hours, verdict.required_approvers.count) == (4, 24, 2)


# --- Step 8

def test_unreachable_opa_denies_and_blocks():
    decision, verdict = govern(checker=access.make_opa_checker(SEED["people"], url="http://localhost:1"))
    assert (decision.decision, decision.rule_id, verdict.route) == ("deny", "opa_unreachable", "block")


def test_missing_policy_escalates():
    _, verdict = govern(policies={})
    assert (verdict.route, verdict.criticality_reasons) == ("escalate", ["policy_missing"])


def test_grader_outage_fails_the_gate():
    def down(**request):
        raise ConnectionError("Claude unreachable")

    grade = llm.make_grader(client=SimpleNamespace(messages=SimpleNamespace(create=down)))
    assert grade("rationale", ["document"])[0] is False


def scripted_caller(*answers):
    """S6 stand-in: these recorded answers in order, recording each prompt."""
    prompts, queue = [], list(answers)

    def call(system, messages, tools):
        prompts.append(messages[0]["content"])
        return fakes.tool_response(**queue.pop(0))

    return call, prompts


def lane_with(*answers):
    call, prompts = scripted_caller(*answers)
    gateway, paid = fakes.make_fake_gateway()
    lane = orchestrate.build_lane(SEED, call, gateway, NOW)
    orchestrate.capture_signal(lane, RAW["s2_refund_monthly_in_policy"])
    lane.bus.drain()
    return lane, paid, prompts


def unsure():
    answer = recorded_answer("s2")
    return {**answer, "tool_input": {**answer["tool_input"], "confidence": 0.3}}


def test_failed_gate_goes_back_to_s6_once_then_succeeds():
    lane, paid, prompts = lane_with(unsure(), recorded_answer("s2"))
    assert len(prompts) == 2 and "previous_attempt_failed_checks" in prompts[1] and "confidence" in prompts[1]
    assert len(paid) == 1 and lane.bus.topics["runs.completed"][-1].payload["outcome"] == "resolved"


def test_gate_failing_twice_escalates_and_pays_nothing():
    lane, paid, prompts = lane_with(unsure(), unsure())
    assert len(prompts) == 2 and paid == {}
    assert lane.bus.topics["runs.completed"][-1].payload["outcome"] == "escalated"
