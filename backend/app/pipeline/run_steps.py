# run_steps.py: the S4 run steps (S5 to S10 for one task), shared by the in-process runner and Temporal.
# Used by: orchestrate.py, temporal_flow.py, run_approvals.py (the S8 part). Uses: stages_orchestrate.py (S4 start), stages_*.py, retrieve_scope.py, contracts_*.py.
from pydantic import BaseModel

from app.pipeline import retrieve_case, retrieve_scope, stages_act, stages_orchestrate_chat, stages_govern, stages_orchestrate, stages_reason, stages_record, stages_retrieve
from app.pipeline.observe import count, log_event
from app.pipeline.retry import call_with_retry
from app.pipeline.contracts_reason import ContextBundle, ContextQuery, ProposedAction
from app.pipeline.contracts_run import Decision, GovernanceVerdict, RunStep
from app.pipeline.contracts_signal import Envelope, Principal, TaskRequest
from app.pipeline.stages_decide import ApprovalState
from app.pipeline.stages_orchestrate import signal_of  # kept here too: run_approvals, stages_learn and summary_sources read it from run_steps

# Config
ACTION_STEP_ID = "step_04"
QUERY_TEXT = "refund window and automatic approval limit"
OUTCOME_FOR_ROUTE = {"block": "blocked", "escalate": "escalated"}
RETRIEVE_ATTEMPTS = 2  # reference doc section 8 (K4): one retry, then escalate context_unavailable
TURNS_KIND = "run_turn"  # records kind keyed by run id: one version per S6 turn, so a later turn knows what was said


class Turn(BaseModel):
    """What the agent did on one message of the run: the next turn reads it (did we already ask the customer?)."""
    signal_id: str
    action_type: str
    arguments: dict


class RunState(BaseModel):
    """One run between steps. A model, so Temporal can store it in workflow history."""
    task: TaskRequest
    action: ProposedAction
    verdict: GovernanceVerdict
    steps: list[RunStep]
    cause: Envelope  # the latest message of this run, so the next one continues the chain
    bundle: ContextBundle | None = None  # kept so an approver's "request changes" can go back to S6
    approval_id: str | None = None
    approval: ApprovalState | None = None


def make_step(lane, step_id: str, kind: str, decision: str, reason: str, refs: list[str]) -> RunStep:
    """One line of the run's story, for the Agent running history screen."""
    return RunStep(step_id=step_id, kind=kind, started_at=lane.now, duration_ms=0, decision=decision, reason=reason, refs=refs)


def retrieve_with_retry(lane, query: ContextQuery, cause: Envelope):
    """S5 with one retry. Publishes the access decision so the audit log sees every read."""
    bundle, decision = call_with_retry(
        lambda: retrieve_case.retrieve_for_run(lane, query),  # knowledge, plus this case's orders and chat
        lambda error: isinstance(error, stages_retrieve.ContextUnavailable), attempts=RETRIEVE_ATTEMPTS, base_delay=0.2,
    )
    lane.bus.publish("access.decisions", "access.decided", decision, "internal", cause)
    return bundle


def close_unavailable(lane, envelope: Envelope, task: TaskRequest, run_id: str) -> None:
    """Context could not be read even after a retry: escalate to a human, act on nothing."""
    step = make_step(lane, "step_01", "retrieval", "context_unavailable", "knowledge store unreachable after one retry", [])
    stages_orchestrate.close_escalated(lane, envelope, task, run_id, step)


def govern_once(lane, task, action, bundle, principal, cause: Envelope, request_text: str):
    """S7 with the lane's policies, access checker and grader. Publishes the access decision."""
    policies = {node["_ref"]["id"]: node for node in lane.graph.latest("policy")}
    _, decision, verdict = stages_govern.govern(task, action, bundle, principal, policies, lane.seed["payments"], lane.seed["cluster_id"], lane.now, lane.new_id, lane.check_access, lane.grade, request_text)
    lane.bus.publish("access.decisions", "access.decided", decision, "governance", cause)
    return decision, verdict


def failed_gates(verdict: GovernanceVerdict) -> str:
    """The failed quality gates as feedback for S6, or "" when none failed."""
    return "; ".join(f"{gate.gate_id}: {gate.detail}" for gate in verdict.quality_gates if not gate.passed)


def propose_and_govern(lane, task: TaskRequest, bundle, principal: Principal, run_id: str, cause: Envelope, feedback: str | None = None):
    """S6 then S7. Reference doc section 8 (K7): a failed quality gate goes back to S6 once, then escalates."""
    signal = signal_of(lane, task.signal_ids[0])
    request_text = (signal.text_masked or "") if signal else ""
    skill = lane.graph.at_version("skill", task.skill_ref.id, task.skill_ref.version) or {}  # the version pinned at route time
    previous = previous_turns(lane, run_id)
    for _ in range(2):
        action = stages_reason.propose(task, bundle, request_text, skill, lane.model, run_id, ACTION_STEP_ID, lane.seed["cluster_id"], feedback, f"{lane.now:%d %B %Y}", previous)
        decision, verdict = govern_once(lane, task, action, bundle, principal, cause, request_text)
        feedback = failed_gates(verdict)
        if not feedback or action.action_type == "escalate":
            break
    remember_turn(lane, run_id, task.signal_ids[0], action)
    return action, decision, verdict


# --- Turns: S6 on each message of a run

def previous_turns(lane, run_id: str) -> list[dict]:
    """The agent's earlier turns in this run, oldest first. An outage reads as none, so S6 asks again rather than refunding."""
    try:
        return [Turn.model_validate(version).model_dump() for version in lane.records.history(TURNS_KIND, run_id)]
    except Exception:
        return []


def remember_turn(lane, run_id: str, signal_id: str, action: ProposedAction) -> None:
    """Best effort: a records outage must not stop the run. The next turn then sees no earlier question, so it asks again."""
    try:
        lane.records.save(TURNS_KIND, run_id, Turn(signal_id=signal_id, action_type=action.action_type, arguments=action.arguments))
    except Exception as error:
        count("s6.turn_not_saved")
        log_event("S6", "turn_not_saved", run_id=run_id, error=type(error).__name__)


def reason_turn(lane, task: TaskRequest, run_id: str, cause: Envelope):
    """S5 then S6 for one message of a run: the bundle, and the agent's proposal, remembered for the next turn."""
    # Step 1: S5, fresh for this message: knowledge, the customer's orders, the chat so far
    signal = signal_of(lane, task.signal_ids[0])
    bundle = retrieve_with_retry(lane, query_for(lane, task, signal, stages_orchestrate.principal_of(lane, task.agent_id), run_id), cause)

    # Step 2: S6 on the pinned skill, knowing what it said in earlier turns
    skill = lane.graph.at_version("skill", task.skill_ref.id, task.skill_ref.version) or {}
    action = stages_reason.propose(task, bundle, (signal.text_masked or "") if signal else "", skill, lane.model, run_id, ACTION_STEP_ID,
                                   lane.seed["cluster_id"], None, f"{lane.now:%d %B %Y}", previous_turns(lane, run_id))
    remember_turn(lane, run_id, task.signal_ids[0], action)
    return bundle, action


def continue_turn(lane, joined: dict, cause: Envelope):
    """A later chat message joined an open run: the run's own task (skill, agent) goes on with that message."""
    signal = signal_of(lane, joined["signal_id"])
    open_run = stages_orchestrate_chat.open_run(lane, signal.conversation_id, joined["agent_id"])
    task = open_run.task.model_copy(update={"signal_ids": [joined["signal_id"]]})
    return reason_turn(lane, task, joined["run_id"], cause)


def query_for(lane, task: TaskRequest, signal, principal: Principal, run_id: str) -> ContextQuery:
    """K4 for this run: what the case names, its entities and domain, and who and which chat it is about."""
    refs = [entity.value_or_token for entity in signal.entities if entity.type == "payment_ref"] if signal else []
    scope = {"entity_ids": retrieve_scope.linked(lane.entities, signal.entity_ids), "domains": [signal.domain] if signal.domain else []} if signal else {}
    customer = signal.actor.ref if signal and signal.actor.type == "customer" else None
    return ContextQuery(run_id=run_id, principal=principal, on_behalf_of=task.on_behalf_of, query_text=QUERY_TEXT, entity_refs=refs, branch="main",
                        node_types=["policy", "fact"], customer_ref=customer, conversation_id=signal.conversation_id if signal else None, **scope)


def start_run(lane, envelope: Envelope) -> RunState | None:
    """S4 starts the run, then S5, S6 and S7. None when it did not start or already closed (context unavailable)."""
    # Step 1: S4 plans the run and hands the chat over; a task it cannot start is closed there
    started = stages_orchestrate.begin_run(lane, envelope)
    if started is None:
        return None

    # Step 2: retrieve what the agent may read about this case: knowledge, the customer's orders, the chat so far
    task = TaskRequest.model_validate(envelope.payload)
    run_id = started.run_id
    principal = stages_orchestrate.principal_of(lane, task.agent_id)  # the graph, as Workflow Studio last saved it
    query = query_for(lane, task, signal_of(lane, task.signal_ids[0]), principal, run_id)
    try:
        bundle = retrieve_with_retry(lane, query, envelope)
    except stages_retrieve.ContextUnavailable:
        close_unavailable(lane, envelope, task, run_id)
        return None

    # Step 3: propose, then govern; a failed gate gets one more try with the reason
    action, decision, verdict = propose_and_govern(lane, task, bundle, principal, run_id, envelope)
    steps = [
        make_step(lane, "step_01", "retrieval", f"{len(bundle.items)} items", f"{bundle.denied_count} withheld", bundle.access_decision_ids),
        make_step(lane, "step_02", "judgment", action.action_type, action.rationale_summary, action.citations),
        make_step(lane, "step_03", "access_check", decision.decision, decision.rule_id, [decision.decision_id]),
    ]
    return RunState(task=task, action=action, verdict=verdict, steps=steps, cause=envelope, bundle=bundle)


def finish_run(lane, run: RunState, outcome: str) -> None:
    """S10: write the trace, then publish the run record and the live UI event."""
    trace = {**run.model_dump(mode="json", exclude={"cause", "bundle"}), "outcome": outcome, "bundle_items": [item.item_id for item in run.bundle.items] if run.bundle else []}
    written = stages_record.write_trace(lane.object_store, stages_record.trace_uri(lane.seed, run.action.run_id), trace)
    record, event = stages_record.record(run.task, run.action, run.steps, outcome, run.approval_id, lane.seed, lane.now, lane.now, trace_written=written)
    lane.bus.publish("runs.completed", "run.completed", record, "recorder", run.cause)
    lane.bus.publish("ui.events", "ui.event", event, "recorder", run.cause)


def tooling(lane) -> dict:
    """What S9 needs from the lane: rate limiter, finished results, one runner per tool, and how to wait."""
    return {**lane.tooling, "runners": {"payment_gateway": lane.gateway, "email": lane.tooling["send_email"]}}


def act_and_finish(lane, run: RunState, decision: Decision | None) -> None:
    """S9 then S10, once governance or a human has cleared the action. A failure closes the run as failed,
    which the console shows live, so a human is told (reference doc section 8, K9)."""
    result = stages_act.act(run.action, run.verdict, decision, lane.seed["tenant_id"], tooling(lane), lane.new_id, lane.now)
    run.cause = lane.bus.publish("actions.executed", "action.executed", result, "worker", run.cause)
    run.steps.append(make_step(lane, ACTION_STEP_ID, "tool", result.status, run.verdict.route, [result.action_id]))
    finish_run(lane, run, "resolved" if result.status == "succeeded" else "failed")


def close_without_acting(lane, run: RunState) -> None:
    """Blocked or escalated by governance: record it, act on nothing."""
    finish_run(lane, run, OUTCOME_FOR_ROUTE[run.verdict.route])
