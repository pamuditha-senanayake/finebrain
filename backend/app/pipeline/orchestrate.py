# orchestrate.py: S4 Orchestrate. Wires S2 and S3 as consumers and runs each task S5 to S10 (Temporal in step 6).
# Used by: tests/test_chain.py. Uses: bus_memory.py, stages_*.py, contracts_*.py, fakes.py (types only).
from dataclasses import dataclass, field
from datetime import datetime

from app.pipeline import stages_govern, stages_intake, stages_reason, stages_record, stages_route
from app.pipeline.bus_memory import MemoryBus
from app.pipeline.contracts_reason import ContextQuery
from app.pipeline.contracts_run import Decision, RunStep
from app.pipeline.contracts_signal import Envelope, Principal, RawSignalEnvelope, Signal, TaskRequest
from app.pipeline.fakes import Gateway, Model, make_id_maker

# Config
ACTION_STEP_ID = "step_04"
QUERY_TEXT = "refund window and automatic approval limit"
OUTCOME_FOR_ROUTE = {"block": "blocked", "escalate": "escalated"}
OUTCOME_FOR_DECISION = {"reject": "blocked", "expired": "escalated", "request_changes": "escalated"}


@dataclass
class Lane:
    """Everything the in-memory pipeline holds. Data only; the functions below act on it."""
    seed: dict
    bus: MemoryBus
    model: Model
    gateway: Gateway
    new_id: object
    now: datetime
    object_store: dict = field(default_factory=dict)
    vault: dict = field(default_factory=dict)
    seen_keys: set = field(default_factory=set)
    signals: dict = field(default_factory=dict)  # signal_id to K2, so S4 can read entities
    pending: dict = field(default_factory=dict)  # approval_id to a paused run


# --- Wiring

def build_lane(seed: dict, model: Model, gateway: Gateway, now: datetime) -> Lane:
    """Create the bus and subscribe one consumer group per stage."""
    new_id = make_id_maker()
    base = {"tenant_id": seed["tenant_id"], "cluster_id": seed["cluster_id"], "env": seed["env"], "branch": "main"}
    lane = Lane(seed=seed, bus=MemoryBus(base, now, new_id), model=model, gateway=gateway, new_id=new_id, now=now)
    lane.bus.subscribe("signals.raw", "normalizer", "S2", lambda envelope: on_raw(lane, envelope))
    lane.bus.subscribe("signals.normalized", "resolver", "S3", lambda envelope: on_signal(lane, envelope))
    lane.bus.subscribe("tasks.created", "worker", "S4", lambda envelope: on_task(lane, envelope))
    lane.bus.subscribe("approvals.decided", "worker", "S8", lambda envelope: on_decision(lane, envelope))
    return lane


def capture_signal(lane: Lane, raw: dict) -> Envelope:
    """Entry point: S1 captures, then the signal goes on signals.raw."""
    k1 = stages_intake.capture(raw, lane.seed["tenant_id"], lane.object_store, lane.now)
    return lane.bus.publish("signals.raw", "signal.raw.captured", k1, "capture")


def decide(lane: Lane, decision: Decision) -> Envelope:
    """Entry point for a human answer from the To review screen."""
    cause = lane.pending[decision.approval_id]["cause"]
    return lane.bus.publish("approvals.decided", "approval.decided", decision, "approvals", cause)


# --- S2 and S3 consumers

def on_raw(lane: Lane, envelope: Envelope) -> None:
    """S2: normalize, or drop silently when it is a redelivery."""
    k1 = RawSignalEnvelope.model_validate(envelope.payload)
    signal = stages_intake.normalize(k1, envelope.event_id, lane.seed["tenant_id"], lane.object_store, lane.vault, lane.seen_keys, lane.new_id)
    if signal is not None:
        lane.bus.publish("signals.normalized", "signal.normalized", signal, "normalizer", envelope)


def on_signal(lane: Lane, envelope: Envelope) -> None:
    """S3: route to a task, or to tasks.unrouted for the Escalations queue."""
    signal = Signal.model_validate(envelope.payload)
    lane.signals[signal.signal_id] = signal
    task = stages_route.route(signal, lane.seed["resolver_rules"], lane.new_id, lane.now)
    if task is None:
        lane.bus.publish("tasks.unrouted", "task.unrouted", signal, "resolver", envelope)
        return
    lane.bus.publish("tasks.created", "task.created", task, "resolver", envelope)


# --- S4 run

def make_step(lane: Lane, step_id: str, kind: str, decision: str, reason: str, refs: list[str]) -> RunStep:
    """One line of the run's story, for the Agent running history screen."""
    return RunStep(step_id=step_id, kind=kind, started_at=lane.now, duration_ms=0, decision=decision, reason=reason, refs=refs)


def start_run(lane: Lane, task: TaskRequest) -> dict:
    """S5, S6 and S7 for one task. Returns the run so far."""
    # Step 1: retrieve what the agent may read about this payment
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
    return {"task": task, "action": action, "verdict": verdict, "steps": steps}


def finish_run(lane: Lane, run: dict, outcome: str, cause: Envelope, approval_id: str | None = None) -> None:
    """S10: publish the run record and the live UI event."""
    record, event = stages_record.record(run["task"], run["action"], run["steps"], outcome, approval_id, lane.seed, lane.now, lane.now)
    lane.bus.publish("runs.completed", "run.completed", record, "recorder", cause)
    lane.bus.publish("ui.events", "ui.event", event, "recorder", cause)


def act_and_finish(lane: Lane, run: dict, decision: Decision | None, cause: Envelope) -> None:
    """S9 then S10, once governance or a human has cleared the action."""
    result = stages_record.act(run["action"], run["verdict"], decision, lane.seed["tenant_id"], lane.gateway, lane.new_id, lane.now)
    executed = lane.bus.publish("actions.executed", "action.executed", result, "worker", cause)
    run["steps"].append(make_step(lane, ACTION_STEP_ID, "tool", result.status, run["verdict"].route, [result.action_id]))
    finish_run(lane, run, "resolved" if result.status == "succeeded" else "failed", executed)


def on_task(lane: Lane, envelope: Envelope) -> None:
    """S4: run the task, then act now, wait for a human, or close it."""
    run = start_run(lane, TaskRequest.model_validate(envelope.payload))
    route = run["verdict"].route
    if route == "execute":
        act_and_finish(lane, run, None, envelope)
        return
    if route != "approval_required":
        finish_run(lane, run, OUTCOME_FOR_ROUTE[route], envelope)
        return

    # Paused: S8 opens the approval and the run waits for approvals.decided
    approval = stages_govern.request_approval(run["action"], run["verdict"], lane.new_id, lane.now)
    requested = lane.bus.publish("approvals.requested", "approval.requested", approval, "approvals", envelope)
    lane.pending[approval.approval_id] = {**run, "cause": requested}
    run["steps"].append(make_step(lane, ACTION_STEP_ID, "human", route, ", ".join(run["verdict"].criticality_reasons), [approval.approval_id]))
    finish_run(lane, run, "awaiting_approval", requested, approval.approval_id)


def on_decision(lane: Lane, envelope: Envelope) -> None:
    """S4 resumes a paused run: approve acts, anything else closes it without acting."""
    decision = Decision.model_validate(envelope.payload)
    run = lane.pending.pop(decision.approval_id)
    if decision.decision == "approve":
        return act_and_finish(lane, run, decision, envelope)
    finish_run(lane, run, OUTCOME_FOR_DECISION.get(decision.decision, "escalated"), envelope, decision.approval_id)
