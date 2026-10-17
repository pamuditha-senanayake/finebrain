# test_decide.py: S8 step 7 (who decides, C4 two approvers and cooling, delegate, takeover, request changes, edits)
# and step 8 (expiry to the delegate then escalation, refused deciders, unknown approvals). One test uses real Temporal.
# Uses: orchestrate.py, run_approvals.py, stages_decide.py, adapters.py, tests/golden.py.
import time
import uuid
from datetime import timedelta

import pytest

from app.pipeline import fakes, observe, orchestrate, run_approvals
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.contracts_reason import ContextBundle, ProposedAction
from app.pipeline.contracts_run import Decision, GovernanceVerdict
from app.pipeline.contracts_signal import Envelope, TaskRequest
from app.pipeline.run_steps import RunState
from tests.golden import NOW, RAW, SEED, golden, recorded_answers

# Config
S3_RAW = RAW["s3_refund_annual_late_large"]
PAID_S3 = 8500000


# --- Helpers

def waiting_lane(seed=SEED, make_adapters=None):
    """A pipeline with the s3 refund (C3, Head of CS) waiting for approval."""
    call, calls = fakes.make_recorded_caller(recorded_answers())
    gateway, paid = fakes.make_fake_gateway()
    options = {"make_adapters": make_adapters} if make_adapters else {}
    lane = orchestrate.build_lane(seed, call, gateway, NOW, **options)
    orchestrate.capture_signal(lane, S3_RAW)
    lane.bus.drain()
    return lane, paid, calls


def approval_id(lane) -> str:
    return lane.bus.topics["approvals.requested"][-1].payload["approval_id"]


def decide(lane, kind: str, by: list[str], approval: str | None = None, **extra) -> None:
    orchestrate.decide(lane, Decision(approval_id=approval or approval_id(lane), decision=kind, decided_by=by, decided_at=NOW, **extra))
    lane.bus.drain()


def outcome(lane) -> str:
    return lane.bus.topics["runs.completed"][-1].payload["outcome"]


# --- Step 7: who decides and what happens

def test_the_accountable_person_is_the_head_of_cs():
    lane, _, _ = waiting_lane()
    assert lane.bus.topics["approvals.requested"][-1].payload["dri_id"] == "head_of_cs"


@pytest.mark.parametrize("by, reason", [(["steward_1"], "not_an_approver"), (["nobody"], "unknown_person"), (["agent_refund_worker"], "requester_cannot_decide")])
def test_wrong_decider_is_refused_and_the_approval_stays_open(by, reason):
    observe.reset_counts()
    lane, paid, _ = waiting_lane()
    decide(lane, "approve", by)
    assert paid == {} and outcome(lane) == "awaiting_approval" and observe.read_count(f"s8.refused.{reason}") == 1


@pytest.mark.parametrize("kind, result, payments", [("approve", "resolved", 1), ("reject", "blocked", 0), ("takeover", "escalated", 0)])
def test_head_of_cs_decides(kind, result, payments):
    lane, paid, _ = waiting_lane()
    decide(lane, kind, ["head_of_cs"])
    assert (outcome(lane), len(paid)) == (result, payments)


def test_delegate_can_then_approve():
    lane, paid, _ = waiting_lane()
    decide(lane, "delegate", ["head_of_cs"], delegated_to="founder")
    decide(lane, "approve", ["founder"])
    assert len(paid) == 1 and outcome(lane) == "resolved"


def test_partial_refund_edit_is_paid_and_overpaying_edit_is_refused():
    lane, paid, _ = waiting_lane()
    too_much = {"payment_ref": "pay_FB_20260830_0047", "amount": {"amount_minor": PAID_S3 + 1, "currency": "LKR"}, "reason_code": "outside_window"}
    decide(lane, "approve", ["head_of_cs"], final_arguments=too_much)
    assert paid == {}
    decide(lane, "approve", ["head_of_cs"], final_arguments={**too_much, "amount": {"amount_minor": 5000000, "currency": "LKR"}})
    assert [payment["arguments"]["amount"]["amount_minor"] for payment in paid.values()] == [5000000]


def test_request_changes_goes_back_to_s6_once():
    lane, paid, calls = waiting_lane()
    first = approval_id(lane)
    decide(lane, "request_changes", ["head_of_cs"], comment="Refund only half, the project used the plan for a month")
    second = approval_id(lane)
    assert second != first and "Refund only half" in calls[-1]["messages"][0]["content"]
    decide(lane, "request_changes", ["head_of_cs"], comment="Still not right")
    assert outcome(lane) == "escalated" and paid == {}


# --- Step 8: expiry, cooling, unknown approvals

def test_expiry_goes_to_the_delegate_then_escalates():
    lane, paid, _ = waiting_lane()
    orchestrate.sweep_expired(lane, NOW + timedelta(hours=73))
    assert lane.pending[approval_id(lane)].approval.assignee == "founder" and outcome(lane) == "awaiting_approval"
    orchestrate.sweep_expired(lane, NOW + timedelta(hours=146))
    assert outcome(lane) == "escalated" and paid == {}


def c4_lane():
    """A memory lane holding a C4 approval: two different leaders, then 24 hours of cooling."""
    gateway, paid = fakes.make_fake_gateway()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], gateway, NOW)
    verdict = GovernanceVerdict.model_validate({**golden("s3", "GovernanceVerdict"), "criticality": 4, "cooling_period_hours": 24,
                                                "required_approvers": {"tier": "L1", "count": 2, "roles": ["dri", "leader"]}})
    cause = Envelope.model_validate({**RUN_ENVELOPE, "payload": golden("s3", "TaskRequest")})
    run = RunState(task=TaskRequest.model_validate(golden("s3", "TaskRequest")), action=ProposedAction.model_validate(golden("s3", "ProposedAction")),
                   verdict=verdict, steps=[], cause=cause, bundle=ContextBundle.model_validate(golden("s3", "ContextBundle")))
    paused = run_approvals.open_approval(lane, run)
    lane.pending[paused.approval_id] = paused
    return lane, paid


RUN_ENVELOPE = {"event_id": "evt_c4", "event_type": "task.created", "schema_version": 1, "tenant_id": SEED["tenant_id"], "cluster_id": SEED["cluster_id"],
                "env": "sandbox", "branch": "main", "occurred_at": NOW, "recorded_at": NOW, "trace_id": "trace_c4", "correlation_id": "corr_c4", "producer": "test"}


def test_c4_needs_two_different_leaders_then_cooling():
    lane, paid = c4_lane()
    decide(lane, "approve", ["head_of_cs"])
    decide(lane, "approve", ["head_of_cs"])  # the same person twice still counts once
    assert lane.pending[approval_id(lane)].approval.final_decision is None
    decide(lane, "approve", ["founder"])
    orchestrate.sweep_expired(lane, NOW + timedelta(hours=23))
    assert paid == {}  # still cooling
    orchestrate.sweep_expired(lane, NOW + timedelta(hours=25))
    assert len(paid) == 1


def test_decision_for_an_unknown_approval_is_refused():
    observe.reset_counts()
    lane, paid, _ = waiting_lane()
    decide(lane, "approve", ["head_of_cs"], approval="apr_does_not_exist")
    assert paid == {} and observe.read_count("s8.refused.unknown_or_closed") == 1


# --- Real Temporal, with timers of a few seconds

@pytest.mark.skipif(bool(missing_infra(frozenset({"temporal"}))), reason="no Temporal on localhost:7233")
def test_temporal_expires_to_the_delegate_then_escalates():
    seed = {**SEED, "tenant_id": f"test_{uuid.uuid4().hex[:8]}", "approval_timing": {"expires_after_seconds": 2, "seconds_per_cooling_hour": 1}}
    lane, paid, _ = waiting_lane(seed, real_adapters(frozenset({"temporal"})))
    try:
        task_id = lane.bus.topics["tasks.created"][-1].payload["task_id"]
        time.sleep(3)
        assert lane.runner.progress(task_id)["phase"] == "awaiting_approval"  # now with the delegate
        time.sleep(3)
        assert lane.runner.progress(task_id)["phase"] == "done" and outcome(lane) == "escalated" and paid == {}
    finally:
        orchestrate.close_lane(lane)
