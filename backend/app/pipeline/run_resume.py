# run_resume.py: a run that asked the customer something goes on when they answer. S4 joined their message to the run;
# here the waiting run is claimed (one worker, one turn, even when two messages land at once), then S5 reads afresh, S6 takes
# the next turn knowing what it asked, and S7 governs; the caller routes the result as for any turn. A wait that ends with
# no answer abandons the run and tells the console. Used by: orchestrate.py (in-process), temporal_flow.py (activities).
# Uses: run_steps.py, run_finish.py, stages_normalize.py (claim), contracts_start.py, observe.py.
from app.pipeline import run_finish, run_steps, stages_orchestrate
from app.pipeline.contracts_signal import Envelope
from app.pipeline.contracts_start import RunContinued
from app.pipeline.observe import count, log_event
from app.pipeline.run_steps import RunState
from app.pipeline.stages_normalize import claim


def waiting_run(lane, run_id: str) -> RunState | None:
    """The run as it was left when it asked the customer, or None when it is not waiting."""
    stored = lane.records.load(run_finish.WAITING_KIND, run_id)
    if not stored or run_steps.stages_orchestrate_chat.run_closed(lane, run_id):
        return None
    return RunState.model_validate(stored)


def resume_run(lane, joined: dict, envelope: Envelope) -> RunState | None:
    """The customer answered: take the run's next turn, S5 to S7. None when another worker took it, or it is not waiting."""
    message = RunContinued.model_validate(joined)
    waiting = waiting_run(lane, message.run_id)
    if waiting is None:
        count("s8.resume.not_waiting")
        log_event("S8", "not_waiting", run_id=message.run_id, signal_id=message.signal_id)
        return None

    # Step 1: one worker per turn; the loser's message is in the chat the winner reads
    turn = len(run_steps.previous_turns(lane, message.run_id))
    if not claim(lane.seen_keys, f"{lane.seed['tenant_id']}:s8:resume:{message.run_id}:{turn}"):
        count("s8.resume.taken")
        return None
    lane.waiting.pop(message.run_id, None)

    # Step 2: S5 afresh for this message, then S6 and S7, on the run's own skill and agent
    task = waiting.task.model_copy(update={"signal_ids": [message.signal_id]})
    principal = stages_orchestrate.principal_of(lane, task.agent_id)
    bundle = run_steps.retrieve_with_retry(lane, run_steps.query_for(lane, task, run_steps.signal_of(lane, message.signal_id), principal, message.run_id), envelope)
    action, decision, verdict = run_steps.propose_and_govern(lane, task, bundle, principal, message.run_id, envelope)
    steps = [*waiting.steps,
             run_steps.make_step(lane, f"{action.step_id}.read", "retrieval", f"{len(bundle.items)} items", f"{bundle.denied_count} withheld", bundle.access_decision_ids),
             run_steps.make_step(lane, f"{action.step_id}.judge", "judgment", action.action_type, action.rationale_summary, action.citations),
             run_steps.make_step(lane, f"{action.step_id}.access", "access_check", decision.decision, decision.rule_id, [decision.decision_id])]
    return RunState(task=task, action=action, verdict=verdict, steps=steps, cause=envelope, bundle=bundle)


def abandon(lane, run_id: str) -> None:
    """No answer in time: close the run as abandoned, so the console shows it and a new message starts fresh."""
    waiting = waiting_run(lane, run_id)
    lane.waiting.pop(run_id, None)
    if waiting is None:
        return
    count("s8.customer_wait_expired")
    run_finish.finish_run(lane, waiting, "abandoned")


def expire_waits(lane, now) -> None:
    """In-process timers (Temporal keeps durable ones): abandon every run whose wait for the customer ended."""
    for run_id, until in list(lane.waiting.items()):
        if until <= now:
            abandon(lane, run_id)
