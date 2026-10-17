# run_approvals.py: S4's approval flow around S8: open, decide, delegate, take over, request changes, expire, cool down.
# Shared by the in-process runner and Temporal. Used by: orchestrate.py, temporal_flow.py. Uses: run_steps.py, stages_decide.py.
from datetime import timedelta

from app.pipeline import run_steps, stages_decide
from app.pipeline.contracts_run import Decision, UiEvent
from app.pipeline.contracts_signal import Envelope, Principal
from app.pipeline.observe import count, log_event
from app.pipeline.run_steps import ACTION_STEP_ID, RunState

# Config
DEFAULT_TIMING = {"expires_after_seconds": 72 * 3600, "seconds_per_cooling_hour": 3600}
CLOSING_OUTCOME = {"reject": "blocked", "takeover": "escalated"}  # anything else that closes is escalated


def timing(lane) -> dict:
    """Approval clocks from the seed, so tests can use seconds instead of days."""
    return {**DEFAULT_TIMING, **lane.seed.get("approval_timing", {})}


def open_approval(lane, run: RunState) -> RunState:
    """S8: publish the approval, record the run as waiting, and return it paused."""
    state = stages_decide.request_approval(run.action, run.verdict, lane.seed["people"], lane.new_id, lane.now, timing(lane)["expires_after_seconds"])
    state.cooling_seconds = run.verdict.cooling_period_hours * timing(lane)["seconds_per_cooling_hour"]
    run.cause = lane.bus.publish("approvals.requested", "approval.requested", state.request, "approvals", run.cause)
    run.approval_id, run.approval = state.request.approval_id, state
    lane.approvals[run.approval_id] = {"cause": run.cause, "task_id": run.task.task_id}
    run.steps.append(run_steps.make_step(lane, ACTION_STEP_ID, "human", run.verdict.route, ", ".join(run.verdict.criticality_reasons), [run.approval_id]))
    run_steps.finish_run(lane, run, "awaiting_approval")
    return run


def tell_console(lane, run: RunState, status: str) -> None:
    """A live 'approval.decided' event, so the To review screen updates."""
    event = UiEvent(type="approval.decided", id=run.approval_id, tenant_id=lane.seed["tenant_id"], cluster_id=lane.seed["cluster_id"], env=lane.seed["env"], display={"status": status, "with": run.approval.assignee}, at=lane.now)
    lane.bus.publish("ui.events", "ui.event", event, "approvals", run.cause)


def refused(lane, run: RunState, decision: Decision) -> str | None:
    """Why a decision cannot count (wrong person, bad edit), or None."""
    paid = (lane.seed["payments"].get(run.action.arguments.get("payment_ref", "")) or {}).get("amount_minor")
    problem = stages_decide.refusal(decision, run.approval, lane.seed["people"], run.task.agent_id)
    return problem or (stages_decide.edit_problem(decision.final_arguments, run.action, paid) if decision.decision == "approve" else None)


def approve(lane, run: RunState, decision: Decision) -> RunState | None:
    """Count the approval. Enough approvers: act now, or after the cooling period (C4)."""
    state = run.approval
    if not stages_decide.count_approvals(state, decision):
        tell_console(lane, run, f"{len(state.approved_by)} of {state.request.required_approvers.count} approved")
        return run
    state.final_decision = decision
    if state.cooling_seconds:
        state.cooling_until = lane.now + timedelta(seconds=state.cooling_seconds)
        tell_console(lane, run, "approved, cooling")
        return run
    run_steps.act_and_finish(lane, run, decision)
    return None


def request_changes(lane, run: RunState, decision: Decision) -> RunState | None:
    """Back to S6 once with the approver's comment, then route the new proposal as usual."""
    if run.approval.changes_requested:
        run_steps.finish_run(lane, run, "escalated")  # a second round of changes needs a person, not another proposal
        return None
    principal = Principal.model_validate(lane.seed["agents"][run.task.agent_id])
    run.action, _, run.verdict = run_steps.propose_and_govern(lane, run.task, run.bundle, principal, run.action.run_id, run.cause, f"The approver asked for changes: {decision.comment}")
    if run.verdict.route == "execute":
        return run_steps.act_and_finish(lane, run, None)
    if run.verdict.route != "approval_required":
        return run_steps.close_without_acting(lane, run)
    reopened = open_approval(lane, run)
    reopened.approval.changes_requested = True
    return reopened


def handle_decision(lane, run: RunState, envelope: Envelope) -> RunState | None:
    """One human decision. Returns the run while it still waits, None once it is closed."""
    decision = Decision.model_validate(envelope.payload)
    problem = refused(lane, run, decision)
    if problem:
        count(f"s8.refused.{problem}")
        log_event("S8", "refused", approval_id=run.approval_id, reason=problem)
        return run
    run.cause = envelope
    count(f"s8.{decision.decision}")
    if decision.decision == "approve":
        return approve(lane, run, decision)
    if decision.decision == "delegate":
        run.approval.assignee = decision.delegated_to
        tell_console(lane, run, "delegated")
        return run
    if decision.decision == "request_changes":
        return request_changes(lane, run, decision)
    run_steps.finish_run(lane, run, CLOSING_OUTCOME.get(decision.decision, "escalated"))
    return None


def expire(lane, run: RunState) -> RunState | None:
    """Nobody decided in time: the delegate gets it once; after that, a human queue. Never auto approves."""
    count("s8.expired")
    if stages_decide.hand_to_delegate(run.approval, lane.seed["people"], lane.now):
        tell_console(lane, run, "expired, now with the delegate")
        return run
    run_steps.finish_run(lane, run, "escalated")
    return None


def release(lane, run: RunState) -> None:
    """The cooling period is over: act on the approved decision."""
    run_steps.act_and_finish(lane, run, run.approval.final_decision)
