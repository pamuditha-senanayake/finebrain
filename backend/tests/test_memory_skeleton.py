# test_memory_skeleton.py: stage 4 of the living memory. One refund walks every new seam, K16 trace, K17 area match,
# K18 drift and K19 skill draft, and each message survives a round trip through JSON as it will on Kafka.
# Uses: app/pipeline/stages_memory.py, store_patterns.py, contracts_memory.py, contracts_run.py, contracts_reason.py.
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app.pipeline import stages_memory as memory
from app.pipeline.contracts_memory import DriftSubject, TracePolicy
from app.pipeline.contracts_reason import AccessDecision
from app.pipeline.contracts_run import Cost, RunRecord, RunStep
from app.pipeline.contracts_signal import VersionRef
from app.pipeline.store_patterns import PATTERN_BUDGET, MemoryPatterns, Pattern

# Config
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
TENANT = "finebase-hq"
SKILL = VersionRef(id="refund-standard", version=4, branch="main", commit_id="c-41")
WINDOW = TracePolicy(policy_ref=VersionRef(id="refund-window", version=3, branch="main", commit_id="c-30"), valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc), valid_to=None)
STRIPE_STEPS = ["refund_asked", "order_checked", "refund_issued", "customer_told"]


def step(n: int, kind: str, activity: str, reason: str = "") -> RunStep:
    return RunStep(step_id=f"s{n}", kind=kind, started_at=NOW, duration_ms=10, decision="ok", reason=reason, refs=[], activity_id=activity)


def refund_run(run_id: str, outcome: str = "resolved", extra_step: bool = False) -> RunRecord:
    steps = [step(1, "retrieval", "context_read"), step(2, "judgment", "action_proposed", "12 days since purchase, inside the 30-day window"),
             step(3, "access_check", "access_allowed"), step(4, "tool", "refund_issued")]
    if extra_step:
        steps.insert(3, step(9, "quality_gate", "gate_passed"))
    return RunRecord(run_id=run_id, task_id=f"task-{run_id}", agent_id="a-refund", skill_ref=SKILL, outcome=outcome, steps=steps, template_fills=[],
                     human_touch=False, cost=Cost(input_tokens=1, output_tokens=1, usd_micro=1), latency_ms=900, trace_object_uri=f"s3://t/{run_id}",
                     decided_by="auto by policy")


def decision(run_id: str, allowed: bool = True) -> AccessDecision:
    return AccessDecision(decision_id=f"d-{run_id}", decision="allow" if allowed else "deny", rule_id="cap.refund", reason="capability",
                          latency_ms=4, principal_id="a-refund", action="refund:issue", run_id=run_id, effective_tier="confidential")


def trace(run_id: str, **run_args) -> memory.TraceRecord:
    allowed = run_args.pop("allowed", True)
    return memory.trace_of_run(refund_run(run_id, **run_args), TENANT, "customer_care", NOW, f"conv-{run_id}", [WINDOW], [memory.access_of(decision(run_id, allowed))])


def survives_json(message: BaseModel) -> bool:
    return type(message).model_validate_json(message.model_dump_json()) == message


def test_a_refund_walks_trace_match_and_learns_a_pattern():
    # Step 1: the run becomes a trace with its steps, rules, access and why (K16)
    first = trace("r1")
    assert first.steps == ["context_read", "action_proposed", "access_allowed", "refund_issued"]
    assert first.why == ["12 days since purchase, inside the 30-day window"]
    assert [a.decision for a in first.access] == ["allow"] and first.policy_check == "within" and survives_json(first)

    # Step 2: the area has no patterns yet, so the first trace is a surprise (K17)
    store = MemoryPatterns(TENANT)
    surprise = memory.triage(first, store)
    assert surprise.match == "surprise" and surprise.pattern_id is None and survives_json(surprise)

    # Step 3: a person confirms it; the same work again is normal and counts, and one step more is still normal
    memory.confirm(first, store)
    again = memory.triage(trace("r2"), store)
    near = memory.triage(trace("r3", extra_step=True), store)
    assert (again.match, again.similarity) == ("normal", 1.0)
    assert (near.match, near.similarity) == ("normal", memory.NEAR_SIMILARITY)
    assert store.area_patterns("customer_care")[memory.pattern_key(first)].count == 2


def test_a_different_ending_is_a_surprise():
    store = MemoryPatterns(TENANT)
    memory.confirm(trace("r1"), store)
    escalated = trace("r4", outcome="escalated")
    assert escalated.policy_check == "outside"
    assert memory.triage(escalated, store).match == "surprise"


def test_security_drift_has_zero_tolerance_and_no_draft():
    flag = memory.security_drift(trace("r5", allowed=False), NOW)
    assert flag and flag.kind == "security" and flag.fix is None and flag.state == "detected" and survives_json(flag)
    assert memory.security_drift(trace("r6"), NOW) is None


def test_skill_drift_carries_a_draft_fix_not_yet_sent():
    skill = DriftSubject(type="skill", id="refund-standard", name="Refund inside policy")
    flag = memory.skill_drift(TENANT, "customer_care", skill, [0.9, 0.92, 0.91, 0.62], ["tr-r4"], "Check the plan type first", NOW)
    assert flag and flag.state == "detected" and flag.fix.summary == "Check the plan type first" and survives_json(flag)
    assert memory.skill_drift(TENANT, "customer_care", skill, [0.9, 0.88], [], "", NOW) is None


def test_policy_drift_uses_the_spike_bar():
    policy = DriftSubject(type="policy", id="refund-window@v3", name="Refund window")
    flag = memory.policy_drift(TENANT, "customer_care", policy, [1, 0, 1, 2, 15], ["tr-stripe-1"], "Refund window: 30 to 45 days", NOW)
    assert flag and flag.kind == "policy" and flag.latest == 15 and survives_json(flag)
    assert memory.policy_drift(TENANT, "customer_care", policy, [4, 5, 4, 6], [], "", NOW) is None


def stripe_refund(n: int, outcome: str = "Refunded by a person"):
    return memory.trace_of_outside(TENANT, f"stripe-{n}", "customer_care", NOW - timedelta(hours=n), STRIPE_STEPS, outcome, "outside", [WINDOW])


def test_a_steady_pattern_no_skill_covers_becomes_a_draft():
    store = MemoryPatterns(TENANT)
    refunds = [stripe_refund(n) for n in range(24)]
    pattern = memory.confirm(refunds[0], store)
    for refund in refunds:
        memory.triage(refund, store)
    draft = memory.skill_draft(pattern, refunds[0], same_steps_total=26, latest_week_share=0.9)
    assert draft and draft.support == 24 and draft.steps == STRIPE_STEPS and draft.state == "draft" and survives_json(draft)
    # A pattern a skill already covers, or with too little support, drafts nothing
    assert memory.skill_draft(pattern, trace("r7"), 26, 0.9) is None
    assert memory.skill_draft(Pattern("pt-x", "k", STRIPE_STEPS, count=10), refunds[0], 10, 0.9) is None


def test_an_area_never_holds_more_patterns_than_its_budget():
    store = MemoryPatterns(TENANT)
    added = [memory.confirm(stripe_refund(n, outcome=f"ending {n}"), store) for n in range(PATTERN_BUDGET + 1)]
    assert all(added[:-1]) and added[-1] is None
    assert len(store.area_patterns("customer_care")) == PATTERN_BUDGET
