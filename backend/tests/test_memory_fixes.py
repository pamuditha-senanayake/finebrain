# test_memory_fixes.py: stage 6 of the living memory, from drift to a fix an L1 user decides, through the real Studio and
# S8 approvals. A policy drift drafts the new window as a change request at L1 level; the drift waits, then is approved
# (and the 14-day re-check starts) or goes back to detected with L1's reason. A skill drift adds the step people now take.
# Security drift is an incident for the L1 leaders, with no draft. The Distiller's night runs the drift checks.
# Uses: app/api/memory_fixes.py, studio_approvals.py, distiller.py, stages_memory_drift.py, tests/studio_helpers.py.
from app.api import distiller
from app.api.studio_state import Studio
from app.pipeline import stages_memory_drift as drift
from app.pipeline.contracts_memory import DriftFix, DriftFlag, DriftSubject
from tests.studio_helpers import FOUNDER, build, decide

# Config
POLICY, SKILL = "policy_refund", "skill_refund_handling"


def raised(lane, kind: str, subject: str, fix: str | None) -> DriftFlag:
    flag = DriftFlag(flag_id=f"dr-{kind}-{subject}", tenant_id=lane.seed["tenant_id"], kind=kind, area="customer_care",
                     subject=DriftSubject(type="agent" if kind == "security" else kind, id=subject, name=subject), summary="People work differently",
                     usual=1, latest=9, evidence_trace_ids=["tr-1"], state="detected", fix=DriftFix(summary=fix, change_request_id=None) if fix else None,
                     recheck=None, reopened_note=None, raised_at=lane.now)
    kept = drift.raise_drift(lane, flag)
    lane.bus.drain()
    return lane.drift.get(kept.flag_id)


def change_of(lane, flag: DriftFlag) -> dict:
    return lane.records.load("change_request", flag.fix.change_request_id)


def test_a_policy_drift_becomes_a_change_request_an_l1_user_approves():
    client, lane = build()
    flag = raised(lane, "policy", POLICY, "Refund window: up to 45 days, as people now refund")
    record = change_of(lane, flag)
    approval = lane.records.load("approval", record["approval_id"])
    # Step 1: the new window is drafted at L1 level, and the drift waits for the L1 user
    assert record["input"]["patch"]["fields"] == {"param.days": 45} and record["criticality"] >= 3
    assert approval["required_approvers"]["tier"] == "L1" and flag.state == "awaiting_approval"
    # Step 2: approved, it merges; the drift is approved and its 14-day re-check starts
    assert decide(client, lane, record["approval_id"], FOUNDER).status_code == 200
    after = lane.drift.get(flag.flag_id)
    assert after.state == "approved" and after.recheck.result == "watching" and (after.recheck.until - lane.now).days == 14
    assert Studio.of(lane).items[POLICY]["fields"]["param.days"] == 45


def test_a_rejected_fix_sends_the_drift_back_with_l1s_reason():
    client, lane = build()
    flag = raised(lane, "policy", POLICY, "Refund window: up to 45 days, as people now refund")
    decide(client, lane, change_of(lane, flag)["approval_id"], FOUNDER, "reject")
    after = lane.drift.get(flag.flag_id)
    assert after.state == "detected" and after.reopened_note == "L1 rejected the fix" and after.fix.change_request_id is None
    assert Studio.of(lane).items[POLICY]["fields"]["param.days"] == 30


def test_a_skill_drift_drafts_the_step_people_now_take():
    _, lane = build()
    flag = raised(lane, "skill", SKILL, "Check the plan type before refunding")
    assert change_of(lane, flag)["input"]["patch"]["fields"]["steps"][-1] == "Check the plan type before refunding"


def test_a_drift_that_cannot_be_drafted_still_goes_to_l1():
    _, lane = build()
    flag = raised(lane, "policy", POLICY, "Review this policy: people now often work outside it")
    assert flag.state == "sent_to_l1" and flag.fix.change_request_id is None
    assert lane.records.list_kind("notification")


def test_security_drift_is_an_incident_for_the_l1_leaders_with_no_draft():
    _, lane = build()
    flag = raised(lane, "security", "agent_refund_worker", None)
    notices = [n for n in lane.records.list_kind("notification") if n["title"].startswith("Security drift")]
    assert flag.state == "sent_to_l1" and flag.fix is None and notices


def test_the_night_catches_up_on_a_decision_and_runs_the_drift_checks():
    client, lane = build()
    flag = raised(lane, "policy", POLICY, "Refund window: up to 45 days, as people now refund")
    lane.drift.move(flag.model_copy(update={"state": "sent_to_l1"}), lane.now, "as if the waiting message were lost")
    decide(client, lane, change_of(lane, flag)["approval_id"], FOUNDER)
    lane.drift.move(lane.drift.get(flag.flag_id).model_copy(update={"state": "sent_to_l1"}), lane.now, "as if the decision message were lost")
    run = distiller.distill(lane, None, "test")
    assert run["memory"]["drift_synced"] == 1 and lane.drift.get(flag.flag_id).state == "approved" and "skill_drift" in run["memory"]["drift"]
