# test_memory_drift.py: stage 6 of the living memory, drift on real data. A run's trace names the policies it was held to;
# a finished action whose access said deny raises one security flag at once; each night reads skill and policy drift from
# the pattern counts and drafts skills from steady patterns; an approved fix is re-checked for 14 days. The drift store
# gives the same answers in memory and on Postgres, and two workers raising one drift at once make one flag.
# Uses: app/pipeline/stages_memory_drift.py, store_drift.py, stages_memory_flow.py, tests/test_chain.py, tests/test_memory_skeleton.py.
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from app.pipeline import stages_memory as memory
from app.pipeline import stages_memory_drift as drift
from app.pipeline import store_postgres
from app.pipeline.contracts_memory import DriftFlag, DriftRecheck, DriftSubject, TraceAccess
from app.pipeline.stages_learn import week_of, zone_of
from app.pipeline.store_drift import MemoryDrift, PostgresDrift
from tests.test_chain import payloads, run_sample

# Config
POSTGRES_UP = store_postgres.database_is_up()
STORES = [MemoryDrift] + ([lambda t: PostgresDrift(store_postgres.connect(), t)] if POSTGRES_UP else [])
IDS = ["memory", "postgres"][: len(STORES)]


def flag(lane_now, subject: str = "a-refund", kind: str = "security", evidence: str = "tr-1") -> DriftFlag:
    return DriftFlag(flag_id=f"dr-{kind}-{subject}", tenant_id="t", kind=kind, area="customer_care", subject=DriftSubject(type="agent", id=subject, name=subject),
                     summary="s", usual=0, latest=1, evidence_trace_ids=[evidence], state="detected", fix=None, recheck=None, reopened_note=None, raised_at=lane_now)


def week(lane, weeks_ago: int):
    return week_of(lane.now - timedelta(weeks=weeks_ago), zone_of(lane))


def counted(lane, area: str, key_skill: str, steps: list[str], outcome: str, check: str, per_week: list[int], trace=None):
    """A pattern counted per week, oldest first, ending this week; its traces are saved when one is given."""
    pattern = lane.patterns.add(area, "|".join([area, key_skill, ">".join(steps), outcome, check]), steps)
    for n, many in enumerate(per_week):
        for i in range(many):
            trace_id = f"tr-{pattern.pattern_id}-{n}-{i}"
            lane.patterns.count(pattern, week(lane, len(per_week) - 1 - n), trace_id)
            if trace:
                lane.traces.save(trace.model_copy(update={"trace_id": trace_id}))
    return pattern


# --- The drift store

@pytest.mark.parametrize("make", STORES, ids=IDS)
def test_one_subject_has_one_open_flag_and_more_evidence_joins_it(make):
    store = make(f"test_drift_{uuid.uuid4().hex[:8]}")
    from tests.golden import NOW
    first, new = store.raise_flag(flag(NOW))
    again, new_again = store.raise_flag(flag(NOW, evidence="tr-2"))
    assert new and not new_again and again.flag_id == first.flag_id and again.evidence_trace_ids == ["tr-2", "tr-1"]
    store.move(again.model_copy(update={"state": "resolved"}), NOW, "resolved")
    later, new_later = store.raise_flag(flag(NOW + timedelta(days=1)))
    assert new_later and later.flag_id != first.flag_id and store.get(first.flag_id).state == "resolved"
    assert [e["state"] for e in store.history(first.flag_id)] == ["detected", "resolved"] and store.in_state("detected") == [later]


@pytest.mark.skipif(not POSTGRES_UP, reason="no Postgres on localhost:5433")
def test_two_workers_raising_one_drift_at_once_make_one_flag():
    from tests.golden import NOW
    tenant = f"test_drift_{uuid.uuid4().hex[:8]}"
    stores = [PostgresDrift(store_postgres.connect(), tenant) for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda i: stores[i].raise_flag(flag(NOW, evidence=f"tr-{i}")), range(2)))
    assert [new for _, new in results].count(True) == 1 and len(stores[0].in_state("detected")) == 1


# --- Security drift, at once

def test_a_runs_trace_names_the_policies_its_workflow_holds_it_to():
    lane, _ = run_sample("s2")
    trace = memory.TraceRecord.model_validate(payloads(lane, "traces.recorded")[0])
    assert trace.policies and trace.policies[0].policy_ref.id == "policy_refund"


def test_a_finished_action_whose_access_said_deny_raises_one_security_flag():
    lane, _ = run_sample("s2")
    trace = memory.TraceRecord.model_validate(payloads(lane, "traces.recorded")[0])
    deny = TraceAccess(decision_id="d-deny", action="refund:issue", principal_id="agent_x", on_behalf_of=None, decision="deny", effective_tier="internal")
    for n in range(2):  # the same agent twice: one flag, more evidence
        bad = trace.model_copy(update={"trace_id": f"tr-bad-{n}", "run_id": f"run_bad_{n}", "access": [*trace.access, deny]})
        lane.traces.save(bad)
        lane.bus.publish("traces.recorded", "trace.recorded", bad, "test")
    lane.bus.drain()
    flags = payloads(lane, "drift.flags")
    assert len(flags) == 1 and flags[0]["kind"] == "security" and flags[0]["fix"] is None
    kept = lane.drift.get(flags[0]["flag_id"])
    assert kept.evidence_trace_ids == ["tr-bad-1", "tr-bad-0"] and lane.records.load(drift.REVIEW_KIND, kept.flag_id)


# --- The night: skill and policy drift, skill drafts

def test_a_skill_whose_usual_path_loses_its_share_drifts_with_a_draft_fix():
    lane, _ = run_sample("s2")
    counted(lane, "finance", "skill_dunning", ["invoice_read", "reminder_sent"], "resolved", "within", [9, 10, 9, 10, 2])
    counted(lane, "finance", "skill_dunning", ["invoice_read", "plan_checked", "call_made"], "resolved", "within", [1, 0, 1, 0, 8])
    result = drift.night(lane)
    held = lane.drift.open_flag("skill", "skill_dunning")
    assert result["skill_drift"] == 1 and held.state == "detected" and "plan_checked → call_made" in held.fix.summary


def test_work_outside_a_policy_spiking_drifts_with_a_new_window_drafted():
    lane, _ = run_sample("s2")
    late = memory.TraceRecord.model_validate(payloads(lane, "traces.recorded")[0]).model_copy(update={"why": ["43 days since purchase, window is 30"], "policy_check": "outside"})
    counted(lane, "customer_care", "none", ["refund_by_hand"], "refunded", "outside", [1, 0, 1, 1, 0, 9], trace=late)
    drift.night(lane)
    held = lane.drift.open_flag("policy", "policy_refund")
    assert held and held.fix.summary == "Refund window: up to 45 days, as people now refund"


def test_a_steady_pattern_no_skill_covers_becomes_one_skill_draft():
    lane, _ = run_sample("s2")
    trace = memory.TraceRecord.model_validate(payloads(lane, "traces.recorded")[0]).model_copy(update={"skill": None})
    counted(lane, "operations", "none", ["vendor_read", "po_raised"], "resolved", "within", [6, 6, 6, 6], trace=trace)
    assert drift.night(lane)["skill_drafts"] == 1 and drift.night(lane)["skill_drafts"] == 0
    assert len(payloads(lane, "skills.drafted")) == 1


# --- The 14-day re-check

def approved(lane, subject: str, until_days: int) -> DriftFlag:
    kept, _ = lane.drift.raise_flag(flag(lane.now, subject=subject))
    return lane.drift.move(kept.model_copy(update={"state": "approved", "recheck": DriftRecheck(until=lane.now + timedelta(days=until_days), result="watching")}), lane.now, "approved")


def test_fourteen_quiet_days_resolve_a_drift_and_a_return_reopens_it():
    lane, _ = run_sample("s2")
    approved(lane, "quiet", until_days=-1)
    back = approved(lane, "back", until_days=10)
    drift.raise_drift(lane, flag(lane.now + timedelta(minutes=1), subject="back"))  # the same drift during the re-check
    assert drift.recheck(lane) == {"resolved": 1, "reopened": 1}
    assert lane.drift.open_flag("security", "back").state == "detected" and "did not hold" in lane.drift.get(back.flag_id).reopened_note
    assert lane.drift.in_state("resolved")[0].subject.id == "quiet"
