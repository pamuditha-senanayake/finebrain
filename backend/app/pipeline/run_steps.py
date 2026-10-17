# run_steps.py: the S4 run steps (S5 to S10 for one task), shared by the in-process runner and Temporal.
# Used by: orchestrate.py (in-process), temporal_flow.py (activities). Uses: stages_*.py, contracts_*.py.
from pydantic import BaseModel

from app.pipeline import stages_govern, stages_reason, stages_record
from app.pipeline.contracts_reason import ContextQuery, ProposedAction
from app.pipeline.contracts_run import Decision, GovernanceVerdict, RunStep
from app.pipeline.contracts_signal import Envelope, Principal, TaskRequest

# Config
ACTION_STEP_ID = "step_04"
QUERY_TEXT = "refund window and automatic approval limit"
OUTCOME_FOR_ROUTE = {"block": "blocked", "escalate": "escalated"}
OUTCOME_FOR_DECISION = {"reject": "blocked", "expired": "escalated", "request_changes": "escalated"}


class RunState(BaseModel):
    """One run between steps. A model, so Temporal can store it in workflow history."""
    task: TaskRequest
    action: ProposedAction
    verdict: GovernanceVerdict
    steps: list[RunStep]
    cause: Envelope  # the latest message of this run, so the next one continues the chain
    approval_id: str | None = None


def make_step(lane, step_id: str, kind: str, decision: str, reason: str, refs: list[str]) -> RunStep:
    """One line of the run's story, for the Agent running history screen."""
    return RunStep(step_id=step_id, kind=kind, started_at=lane.now, duration_ms=0, decision=decision, reason=reason, refs=refs)


def start_run(lane, envelope: Envelope) -> RunState:
    """S5, S6 and S7 for the task in this envelope."""
    # Step 1: retrieve what the agent may read about this payment
    task = TaskRequest.model_validate(envelope.payload)
    run_id = lane.new_id("run")
    principal = Principal.model_validate(lane.seed["agents"][task.agent_id])
    refs = [entity.value_or_token for entity in lane.signals[task.signal_ids[0]].entities if entity.type == "payment_ref"]
    query = ContextQuery(run_id=run_id, principal=principal, on_behalf_of=None, query_text=QUERY_TEXT, entity_refs=refs, branch="main", node_types=["policy", "fact"])
    bundle = stages_reason.retrieve(query, lane.seed["knowledge"], lane.new_id)

    # Step 2: propose, then govern
    action = stages_reason.propose(task, bundle, lane.model, run_id, ACTION_STEP_ID, lane.seed["cluster_id"])
    _, decision, verdict = stages_govern.govern(task, action, bundle, principal, lane.seed["refund_policy"], lane.seed["payments"], lane.seed["cluster_id"], lane.now, lane.new_id)
    steps = [
        make_step(lane, "step_01", "retrieval", f"{len(bundle.items)} items", "context for the task", bundle.access_decision_ids),
        make_step(lane, "step_02", "judgment", action.action_type, action.rationale_summary, action.citations),
        make_step(lane, "step_03", "access_check", decision.decision, decision.rule_id, [decision.decision_id]),
    ]
    return RunState(task=task, action=action, verdict=verdict, steps=steps, cause=envelope)


def finish_run(lane, run: RunState, outcome: str) -> None:
    """S10: publish the run record and the live UI event."""
    record, event = stages_record.record(run.task, run.action, run.steps, outcome, run.approval_id, lane.seed, lane.now, lane.now)
    lane.bus.publish("runs.completed", "run.completed", record, "recorder", run.cause)
    lane.bus.publish("ui.events", "ui.event", event, "recorder", run.cause)


def act_and_finish(lane, run: RunState, decision: Decision | None) -> None:
    """S9 then S10, once governance or a human has cleared the action."""
    result = stages_record.act(run.action, run.verdict, decision, lane.seed["tenant_id"], lane.gateway, lane.new_id, lane.now)
    run.cause = lane.bus.publish("actions.executed", "action.executed", result, "worker", run.cause)
    run.steps.append(make_step(lane, ACTION_STEP_ID, "tool", result.status, run.verdict.route, [result.action_id]))
    finish_run(lane, run, "resolved" if result.status == "succeeded" else "failed")


def close_without_acting(lane, run: RunState) -> None:
    """Blocked or escalated by governance: record it, act on nothing."""
    finish_run(lane, run, OUTCOME_FOR_ROUTE[run.verdict.route])


def open_approval(lane, run: RunState) -> RunState:
    """S8: publish the approval, record the run as waiting, and return it paused."""
    approval = stages_govern.request_approval(run.action, run.verdict, lane.new_id, lane.now)
    run.cause = lane.bus.publish("approvals.requested", "approval.requested", approval, "approvals", run.cause)
    run.approval_id = approval.approval_id
    lane.approvals[approval.approval_id] = {"cause": run.cause, "task_id": run.task.task_id}
    run.steps.append(make_step(lane, ACTION_STEP_ID, "human", run.verdict.route, ", ".join(run.verdict.criticality_reasons), [approval.approval_id]))
    finish_run(lane, run, "awaiting_approval")
    return run


def resume_after_decision(lane, run: RunState, envelope: Envelope) -> None:
    """Approve acts. Anything else closes the run without acting. Never auto approves."""
    decision = Decision.model_validate(envelope.payload)
    run.cause = envelope
    if decision.decision == "approve":
        return act_and_finish(lane, run, decision)
    finish_run(lane, run, OUTCOME_FOR_DECISION.get(decision.decision, "escalated"))
