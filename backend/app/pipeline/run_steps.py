# run_steps.py: the S4 run steps (S5 to S10 for one task), shared by the in-process runner and Temporal.
# Used by: orchestrate.py (in-process), temporal_flow.py (activities). Uses: stages_*.py, contracts_*.py.
from pydantic import BaseModel

from app.pipeline import stages_decide, stages_govern, stages_reason, stages_record, stages_retrieve
from app.pipeline.retry import call_with_retry
from app.pipeline.contracts_reason import ContextQuery, ProposedAction
from app.pipeline.contracts_run import Decision, GovernanceVerdict, RunStep
from app.pipeline.contracts_signal import Envelope, Principal, TaskRequest

# Config
ACTION_STEP_ID = "step_04"
QUERY_TEXT = "refund window and automatic approval limit"
OUTCOME_FOR_ROUTE = {"block": "blocked", "escalate": "escalated"}
OUTCOME_FOR_DECISION = {"reject": "blocked", "expired": "escalated", "request_changes": "escalated"}
RETRIEVE_ATTEMPTS = 2  # reference doc section 8 (K4): one retry, then escalate context_unavailable


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


def retrieve_with_retry(lane, query: ContextQuery, cause: Envelope):
    """S5 with one retry. Publishes the access decision so the audit log sees every read."""
    bundle, decision = call_with_retry(
        lambda: stages_retrieve.retrieve(query, lane.chunks, lane.embed, lane.rerank, lane.seed["people"], lane.new_id, lane.now),
        lambda error: isinstance(error, stages_retrieve.ContextUnavailable), attempts=RETRIEVE_ATTEMPTS, base_delay=0.2,
    )
    lane.bus.publish("access.decisions", "access.decided", decision, "internal", cause)
    return bundle


def close_unavailable(lane, envelope: Envelope, task: TaskRequest, run_id: str) -> None:
    """Context could not be read even after a retry: escalate to a human, act on nothing."""
    step = make_step(lane, "step_01", "retrieval", "context_unavailable", "knowledge store unreachable after one retry", [])
    record, event = stages_record.record(task, None, [step], "escalated", None, lane.seed, lane.now, lane.now, run_id=run_id)
    lane.bus.publish("runs.completed", "run.completed", record, "recorder", envelope)
    lane.bus.publish("ui.events", "ui.event", event, "recorder", envelope)


def govern_once(lane, task, action, bundle, principal, cause: Envelope, request_text: str):
    """S7 with the lane's policies, access checker and grader. Publishes the access decision."""
    policies = {node["_ref"]["id"]: node for node in lane.graph.latest("policy")}
    _, decision, verdict = stages_govern.govern(task, action, bundle, principal, policies, lane.seed["payments"], lane.seed["cluster_id"], lane.now, lane.new_id, lane.check_access, lane.grade, request_text)
    lane.bus.publish("access.decisions", "access.decided", decision, "governance", cause)
    return decision, verdict


def failed_gates(verdict: GovernanceVerdict) -> str:
    """The failed quality gates as feedback for S6, or "" when none failed."""
    return "; ".join(f"{gate.gate_id}: {gate.detail}" for gate in verdict.quality_gates if not gate.passed)


def propose_and_govern(lane, task: TaskRequest, bundle, principal: Principal, run_id: str, cause: Envelope):
    """S6 then S7. Reference doc section 8 (K7): a failed quality gate goes back to S6 once, then escalates."""
    signal = lane.signals[task.signal_ids[0]]
    skill = {node["_ref"]["id"]: node for node in lane.graph.latest("skill")}.get(task.skill_ref.id, {})
    feedback = None
    for _ in range(2):
        action = stages_reason.propose(task, bundle, signal.text_masked or "", skill, lane.model, run_id, ACTION_STEP_ID, lane.seed["cluster_id"], feedback, f"{lane.now:%d %B %Y}")
        decision, verdict = govern_once(lane, task, action, bundle, principal, cause, signal.text_masked or "")
        feedback = failed_gates(verdict)
        if not feedback or action.action_type == "escalate":
            break
    return action, decision, verdict


def start_run(lane, envelope: Envelope) -> RunState | None:
    """S5, S6 and S7 for the task in this envelope. None when the run already closed (context unavailable)."""
    # Step 1: retrieve what the agent may read about this payment
    task = TaskRequest.model_validate(envelope.payload)
    run_id = lane.new_id("run")
    principal = Principal.model_validate(lane.seed["agents"][task.agent_id])
    refs = [entity.value_or_token for entity in lane.signals[task.signal_ids[0]].entities if entity.type == "payment_ref"]
    query = ContextQuery(run_id=run_id, principal=principal, on_behalf_of=task.on_behalf_of, query_text=QUERY_TEXT, entity_refs=refs, branch="main", node_types=["policy", "fact"])
    try:
        bundle = retrieve_with_retry(lane, query, envelope)
    except stages_retrieve.ContextUnavailable:
        close_unavailable(lane, envelope, task, run_id)
        return None

    # Step 2: propose, then govern; a failed gate gets one more try with the reason
    action, decision, verdict = propose_and_govern(lane, task, bundle, principal, run_id, envelope)
    steps = [
        make_step(lane, "step_01", "retrieval", f"{len(bundle.items)} items", f"{bundle.denied_count} withheld", bundle.access_decision_ids),
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
    approval = stages_decide.request_approval(run.action, run.verdict, lane.new_id, lane.now)
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
