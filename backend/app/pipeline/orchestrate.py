# orchestrate.py: S4 Orchestrate. Wires S2, S3 and the task consumers onto a bus, given its adapters.
# Used by: tests/test_chain.py, tests/test_e2e.py. Uses: adapters.py, run_steps.py, recorder.py, stages_*.py, temporal_runner.py (via adapters).
# Each task runs in-process, or as a Temporal workflow when the adapters include a Temporal runner.
from dataclasses import dataclass, field
from datetime import datetime

from app.pipeline import run_approvals, run_steps, stages_intake, stages_normalize, stages_route
from app.pipeline.observe import count, log_event
from app.pipeline.adapters import make_memory_adapters
from app.pipeline.contracts_run import Decision
from app.pipeline.contracts_signal import Envelope, RawSignalEnvelope, Signal
from app.pipeline.fakes import Gateway, Model, make_id_maker, pass_grader
from app.pipeline.recorder import subscribe_recorder


@dataclass
class Lane:
    """Everything one pipeline holds. Data only; the functions below and in run_steps.py act on it."""
    seed: dict
    model: Model
    gateway: Gateway
    now: datetime
    new_id: object
    bus: object
    object_store: object
    vault: object
    seen_keys: object
    records: object
    graph: object
    chunks: object
    embed: object
    rerank: object
    check_access: object
    tooling: dict  # S9: rate limiter, finished results, email sender, how to wait between retries
    grade: object = None  # S7 grader (llm.make_grader); defaults to the fake that passes cited rationales
    choose: object = None  # S3 tie-break (llm.make_chooser); None means close calls go unrouted
    runner: object = None  # TemporalRunner, or None to run tasks in-process
    signals: dict = field(default_factory=dict)  # signal_id to K2, so S4 can read entities
    approvals: dict = field(default_factory=dict)  # approval_id to its cause and task
    pending: dict = field(default_factory=dict)  # approval_id to a paused run (in-process only)


# --- Wiring

def build_lane(seed: dict, model: Model, gateway: Gateway, now: datetime, make_adapters=make_memory_adapters, choose=None, grade=None) -> Lane:
    """Build the adapters, then subscribe one consumer group per stage."""
    new_id = make_id_maker()
    adapters = make_adapters(seed, now, new_id)
    lane = Lane(seed=seed, model=model, gateway=gateway, now=now, new_id=new_id, choose=choose or no_tie_break, grade=grade or pass_grader, **adapters)
    lane.bus.subscribe("signals.raw", "normalizer", "S2", lambda envelope: on_raw(lane, envelope))
    lane.bus.subscribe("signals.normalized", "resolver", "S3", lambda envelope: on_signal(lane, envelope))
    lane.bus.subscribe("tasks.created", "worker", "S4", lambda envelope: on_task(lane, envelope))
    lane.bus.subscribe("approvals.decided", "worker", "S8", lambda envelope: on_decision(lane, envelope))
    subscribe_recorder(lane.bus, lane.records)
    if lane.runner is not None:
        lane.runner.start(lane)
    return lane


def capture_signal(lane: Lane, raw: dict) -> Envelope:
    """Entry point: S1 captures, then the signal goes on signals.raw."""
    k1 = stages_intake.capture(raw, lane.seed["tenant_id"], lane.object_store, lane.now)
    return lane.bus.publish("signals.raw", "signal.raw.captured", k1, "capture")


def decide(lane: Lane, decision: Decision) -> Envelope:
    """Entry point for a human answer from the To review screen."""
    cause = (lane.approvals.get(decision.approval_id) or {}).get("cause")  # unknown ids still go on the bus, to be refused and logged
    return lane.bus.publish("approvals.decided", "approval.decided", decision, "approvals", cause)


def close_lane(lane: Lane) -> None:
    """Stop the Temporal worker, if there is one."""
    if lane.runner is not None:
        lane.runner.stop()


# --- S2 and S3 consumers

def on_raw(lane: Lane, envelope: Envelope) -> None:
    """S2: normalize, or drop silently when it is a redelivery."""
    k1 = RawSignalEnvelope.model_validate(envelope.payload)
    signal = stages_normalize.normalize(k1, envelope.event_id, lane.seed["tenant_id"], lane.object_store, lane.vault, lane.seen_keys, lane.new_id)
    if signal is not None:
        lane.bus.publish("signals.normalized", "signal.normalized", signal, "normalizer", envelope)


def no_tie_break(text: str, options: dict) -> None:
    """Default chooser: no model call, so a close call goes to a human."""
    return None


def on_signal(lane: Lane, envelope: Envelope) -> None:
    """S3: route to a task, to tasks.unrouted for the Escalations queue, or leave documents to Lane B."""
    signal = Signal.model_validate(envelope.payload)
    lane.signals[signal.signal_id] = signal
    task, reason = stages_route.route(signal, stages_route.read_routing(lane.graph), lane.choose, lane.new_id, lane.now)
    if reason == "lane_b":
        return
    if task is None:
        lane.bus.publish("tasks.unrouted", "task.unrouted", signal, "resolver", envelope)
        return
    lane.bus.publish("tasks.created", "task.created", task, "resolver", envelope)


# --- S4 consumers

def on_task(lane: Lane, envelope: Envelope) -> None:
    """S4: hand the task to Temporal, or run it here: act now, wait for a human, or close it."""
    if lane.runner is not None:
        return lane.runner.start_task(envelope)
    run = run_steps.start_run(lane, envelope)
    if run is None:  # closed early: context unavailable, already escalated
        return None
    if run.verdict.route == "execute":
        return run_steps.act_and_finish(lane, run, None)
    if run.verdict.route != "approval_required":
        return run_steps.close_without_acting(lane, run)
    paused = run_approvals.open_approval(lane, run)
    lane.pending[paused.approval_id] = paused


def on_decision(lane: Lane, envelope: Envelope) -> None:
    """S4 hands a decision to the paused run for its approval. Unknown or closed approvals are refused."""
    approval_id = Decision.model_validate(envelope.payload).approval_id
    known = lane.approvals.get(approval_id)
    if known is None or (lane.runner is None and approval_id not in lane.pending):
        count("s8.refused.unknown_or_closed")
        log_event("S8", "refused", approval_id=approval_id, reason="unknown_or_closed")
        return None
    if lane.runner is not None:
        return lane.runner.send_decision(known["task_id"], envelope)
    keep(lane, run_approvals.handle_decision(lane, lane.pending.pop(approval_id), envelope))


def keep(lane: Lane, run) -> None:
    """Still waiting: keep it under its (maybe new) approval id. Closed: forget it."""
    if run is not None:
        lane.pending[run.approval_id] = run


def sweep_expired(lane: Lane, now) -> None:
    """In-process timers (Temporal uses durable ones): move the clock, expire overdue approvals, end cooling periods."""
    lane.now = lane.bus.now = now
    for approval_id, run in list(lane.pending.items()):
        state = run.approval
        if state.cooling_until is not None and state.cooling_until <= now:
            keep(lane, run_approvals.release(lane, lane.pending.pop(approval_id)))
        elif state.final_decision is None and state.request.expires_at <= now:
            keep(lane, run_approvals.expire(lane, lane.pending.pop(approval_id)))
