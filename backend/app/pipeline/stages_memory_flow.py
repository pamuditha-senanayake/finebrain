# stages_memory_flow.py: the living memory on the bus (stage 5b). Three consumers: access decisions are kept by run; a
# finished run becomes a trace (K16 on traces.recorded); each trace is claimed, triaged against its area's patterns
# (K17 on traces.matched), and a surprise becomes one To review item. Every step is safe to repeat: stores ignore
# duplicates, and a claim (Valkey SET NX in production) keeps two workers off one trace at a time.
# Since stage 6 a trace carries the policies its workflow names, and security drift is checked at triage and on a late
# access decision. Used by: orchestrate.py (build_lane), tests/test_memory_flow.py, tests/test_memory_real.py.
# Uses: stages_memory.py, stages_memory_drift.py, run_steps.py (activity_policies), contracts_memory.py, contracts_run.py, contracts_reason.py, item_tags.py, stages_learn.py, stages_normalize.py (claim).
from typing import get_args

from app.pipeline import item_tags, stages_memory_drift
from app.pipeline import stages_memory as memory
from app.pipeline.contracts_memory import Area, AreaMatch, TraceRecord
from app.pipeline.contracts_reason import AccessDecision
from app.pipeline.contracts_run import RunRecord
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.run_steps import activity_policies
from app.pipeline.stages_govern import POLICY_FOR_ACTION
from app.pipeline.observe import count, log_event
from app.pipeline.stages_learn import zone_of
from app.pipeline.stages_normalize import claim

# Config
MATCH_KIND = "memory_match"  # records kind keyed by trace id: the trace's K17, written once
REVIEW_KIND = "memory_review"  # records kind keyed by trace id: a surprise waiting for a person in To review
AREAS = set(get_args(Area))
# A run that pauses publishes its record again when it ends; only the ending is the piece of work, so pauses wait
OPEN_OUTCOMES = {"awaiting_approval", "awaiting_customer"}


class TraceClaimed(Exception):
    """Another worker holds this trace and has not finished. Retryable: a replay after its claim expires carries on."""
    retryable = True


# --- Access decisions

def on_access(lane, envelope) -> None:
    """Keep each decision under its run; one that arrives after the run's trace is attached to it."""
    decision = AccessDecision.model_validate(envelope.payload)
    if not decision.run_id:
        return
    access = memory.access_of(decision)
    lane.traces.add_access(decision.run_id, access)
    lane.traces.attach(f"tr-{decision.run_id}", access)
    trace = lane.traces.get(f"tr-{decision.run_id}")
    if trace and access.decision == "deny" and lane.drift is not None:  # a late deny on a finished action is security drift too; safe to repeat
        stages_memory_drift.check_security(lane, trace, envelope)


def on_task(lane, envelope) -> None:
    """Keep each task's activity, so the run's trace can name the policies its workflow holds it to."""
    task = TaskRequest.model_validate(envelope.payload)
    lane.traces.add_activity(task.task_id, task.activity_id)


# --- Runs to traces

def signal_of(lane, run: RunRecord) -> dict | None:
    """One signal, one task: task_X came from sig_X, read by its key."""
    return lane.records.load("signal", "sig_" + run.task_id.removeprefix("task_"))


def area_of(lane, signal: dict | None) -> str:
    """The domain S2 tagged the signal with; a signal from before step 13a falls back to its cluster's area."""
    domain = (signal or {}).get("domain")
    return domain if domain in AREAS else item_tags.default_domain(lane.seed)


def trace_of(lane, run: RunRecord, envelope) -> TraceRecord:
    signal = signal_of(lane, run)
    started = min((step.started_at for step in run.steps), default=envelope.occurred_at)
    # The policies in force when the work started: those the activity's workflow names, each at the version valid then
    activity = lane.traces.activity_of(run.task_id)
    named = activity_policies(lane, activity) if activity else []
    # A workflow that names none: the policy S7 itself checks for the action the run proposed
    checked = [POLICY_FOR_ACTION[s.decision] for s in run.steps if s.kind == "judgment" and s.decision in POLICY_FOR_ACTION]
    policies = memory.policies_at(lane.graph, list(dict.fromkeys(named or checked)), started)
    return memory.trace_of_run(run, lane.seed["tenant_id"], area_of(lane, signal), started, (signal or {}).get("signal_id", run.task_id), policies, lane.traces.access_of(run.run_id))


def on_run(lane, envelope) -> None:
    """S10's run record, once the run has ended, becomes a trace. It is published when first kept, or again if it was never
    triaged (a crash in between)."""
    run = RunRecord.model_validate(envelope.payload)
    if run.outcome in OPEN_OUTCOMES:
        return
    trace = trace_of(lane, run, envelope)
    first = lane.traces.save(trace)
    if first or not lane.records.load(MATCH_KIND, trace.trace_id):
        lane.bus.publish("traces.recorded", "trace.recorded", lane.traces.get(trace.trace_id), "memory", envelope)
        count("memory.trace_recorded")


# --- Triage

def on_trace(lane, envelope) -> None:
    """Claim, triage, keep the match once, and put a surprise in To review once."""
    trace = TraceRecord.model_validate(envelope.payload)
    # Step 1: done already (a redelivery) means nothing to do; held by another worker means try again later
    if lane.records.load(MATCH_KIND, trace.trace_id):
        return
    if not claim(lane.memory_claims, f"triage:{trace.trace_id}"):
        raise TraceClaimed(trace.trace_id)
    # Step 2: match against the area's patterns, then keep the result before telling anyone
    match = memory.triage(trace, lane.patterns, zone_of(lane))
    if lane.drift is not None:  # before the match is kept, so a failure here is replayed, never skipped as done
        stages_memory_drift.check_security(lane, trace, envelope)
    lane.records.save(MATCH_KIND, trace.trace_id, match)
    if match.match == "surprise":
        raise_for_review(lane, match)
    lane.bus.publish("traces.matched", "trace.matched", match, "memory", envelope)
    log_event("memory", "triaged", trace_id=trace.trace_id, area=match.area, match=match.match)


def raise_for_review(lane, match: AreaMatch) -> None:
    """A surprise waits for a person, once. Their answer (memory.confirm) turns it into a pattern."""
    if lane.records.load(REVIEW_KIND, match.trace_id):
        return
    lane.records.save(REVIEW_KIND, match.trace_id, match)
    count("memory.surprise_raised")


def subscribe_memory(lane) -> None:
    """One consumer group per job, as on Kafka. A lane built without the memory stores skips it."""
    if lane.traces is None or lane.patterns is None:
        return
    lane.bus.subscribe("access.decisions", "memory_access", "S10", lambda envelope: on_access(lane, envelope))
    lane.bus.subscribe("tasks.created", "memory_tasks", "S10", lambda envelope: on_task(lane, envelope))
    lane.bus.subscribe("runs.completed", "memory_traces", "S10", lambda envelope: on_run(lane, envelope))
    lane.bus.subscribe("traces.recorded", "memory_triage", "S13", lambda envelope: on_trace(lane, envelope))
