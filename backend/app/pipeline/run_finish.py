# run_finish.py: the end of a run turn, S9 then S10, shared by the in-process runner, Temporal and S8's approvals. S9 acts
# once; S10 records the outcome and who let the action through. A reply that asks the customer something keeps the run open:
# it is kept where any worker can resume it, until the wait ends. Used by: orchestrate.py, run_approvals.py, run_resume.py,
# temporal_flow.py. Uses: run_steps.py (RunState, steps, turns), stages_act.py, stages_record.py, govern_payments.py, tools_write.py, tools_chat.py.
from datetime import timedelta

from app.pipeline import govern_payments, stages_act, stages_record, tools_chat, tools_write
from app.pipeline.contracts_run import Decision
from app.pipeline.run_steps import OUTCOME_FOR_ROUTE, RunState, make_step, previous_turns
from app.pipeline.tools import TOOLS

# Config
WAITING_KIND = "run_waiting"  # records kind keyed by run id: the run, while it waits for the customer
CUSTOMER_WAIT_SECONDS = 48 * 3600  # no answer by then: the run is abandoned and the console says so; a tenant may set customer_wait_seconds
STUDIO = "studio"  # where a graph node keeps its Studio fields (app/api/studio_model.py)


def finish_run(lane, run: RunState, outcome: str, decided_by: str | None = None) -> None:
    """S10: write the trace (with every turn and the chat so far), then publish the run record and the live UI event."""
    trace = {**run.model_dump(mode="json", exclude={"cause", "bundle"}), "outcome": outcome, "bundle_items": [item.item_id for item in run.bundle.items] if run.bundle else [],
             "turns": previous_turns(lane, run.action.run_id), "chat": [item.item_id for item in run.bundle.items if item.item_id.startswith("msg:")] if run.bundle else []}
    written = stages_record.write_trace(lane.object_store, stages_record.trace_uri(lane.seed, run.action.run_id), trace)
    record, event = stages_record.record(run.task, run.action, run.steps, outcome, run.approval_id, lane.seed, lane.now, lane.now, trace_written=written, decided_by=decided_by)
    lane.bus.publish("runs.completed", "run.completed", record, "recorder", run.cause)
    lane.bus.publish("ui.events", "ui.event", event, "recorder", run.cause)


def tool_endpoint(lane, action_type: str) -> str | None:
    """Where the graph says a tool goes, read by its key, so a change in Studio is what S9 does. None: no tool node yet."""
    versions = [node for node in lane.graph.history("tool", f"tool:{action_type}") if not node.get("_closed")]
    return ((versions[-1].get(STUDIO) or {}).get("fields") or {}).get("endpoint") if versions else None


def tooling(lane, run: RunState) -> dict:
    """What S9 needs for this run: rate limiter, finished results, one runner per endpoint, the graph's endpoints, how to wait."""
    runners = {"shop_database": tools_write.runner(lane, run), "chat": tools_chat.runner(lane, run)}
    endpoints = {name: endpoint for name in TOOLS if (endpoint := tool_endpoint(lane, name))}
    return {**lane.tooling, "runners": runners, "endpoints": endpoints}


def act_and_finish(lane, run: RunState, decision: Decision | None) -> None:
    """S9 then S10, once governance or a human has cleared the action. A failure closes the run as failed,
    which the console shows live, so a human is told (reference doc section 8, K9)."""
    result = stages_act.act(run.action, run.verdict, decision, lane.seed["tenant_id"], tooling(lane, run), lane.new_id, lane.now)
    run.cause = lane.bus.publish("actions.executed", "action.executed", result, "worker", run.cause)
    run.steps.append(make_step(lane, run.action.step_id, "tool", result.status, run.verdict.route, [result.action_id]))
    if result.status == "succeeded" and run.action.action_type == "issue_refund":
        govern_payments.note_refund(lane, run.action.arguments["payment_ref"], run.action.money.amount_minor, run.action.run_id)
    outcome = outcome_after(run, result.status)
    finish_run(lane, run, outcome, decided_by_of(run, decision))
    if outcome == "awaiting_customer":
        wait_for_customer(lane, run)
    return outcome


def outcome_after(run: RunState, status: str) -> str:
    """Resolved, failed, or waiting: a reply that asks the customer something keeps the run open for their answer."""
    if status != "succeeded":
        return "failed"
    asks = run.action.action_type == "reply_customer" and run.action.arguments.get("awaits_customer")
    return "awaiting_customer" if asks else "resolved"


def decided_by_of(run: RunState, decision: Decision | None) -> str | None:
    """Who let the action through: the approvers, or the policy itself when S7 cleared it at C0."""
    if decision is not None:
        return ", ".join(decision.decided_by)
    return "auto by policy" if run.verdict.route == "execute" else None


def wait_for_customer(lane, run: RunState) -> None:
    """Keep the run where any worker can pick it up when the customer answers, until the wait ends."""
    lane.records.save(WAITING_KIND, run.action.run_id, run)
    lane.waiting[run.action.run_id] = lane.now + customer_wait(lane)


def customer_wait(lane) -> timedelta:
    """How long a run waits for the customer's answer, for this tenant."""
    return timedelta(seconds=lane.seed.get("customer_wait_seconds", CUSTOMER_WAIT_SECONDS))


def close_without_acting(lane, run: RunState) -> None:
    """Blocked or escalated by governance: record it, act on nothing."""
    finish_run(lane, run, OUTCOME_FOR_ROUTE[run.verdict.route])
