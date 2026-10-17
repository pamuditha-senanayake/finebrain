# orchestrate.py: S4 Orchestrate. Wires S2, S3 and the task consumers onto a bus, given its adapters.
# Used by: tests/test_chain.py, tests/test_e2e.py. Uses: adapters.py, run_steps.py, recorder.py, stages_*.py, temporal_runner.py (via adapters).
# Each task runs in-process, or as a Temporal workflow when the adapters include a Temporal runner.
from dataclasses import dataclass, field
from datetime import datetime

from app.pipeline import run_steps, stages_intake, stages_normalize, stages_route
from app.pipeline.adapters import make_memory_adapters
from app.pipeline.contracts_run import Decision
from app.pipeline.contracts_signal import Envelope, RawSignalEnvelope, Signal
from app.pipeline.fakes import Gateway, Model, make_id_maker
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
    runner: object = None  # TemporalRunner, or None to run tasks in-process
    signals: dict = field(default_factory=dict)  # signal_id to K2, so S4 can read entities
    approvals: dict = field(default_factory=dict)  # approval_id to its cause and task
    pending: dict = field(default_factory=dict)  # approval_id to a paused run (in-process only)


# --- Wiring

def build_lane(seed: dict, model: Model, gateway: Gateway, now: datetime, make_adapters=make_memory_adapters) -> Lane:
    """Build the adapters, then subscribe one consumer group per stage."""
    new_id = make_id_maker()
    adapters = make_adapters(seed, now, new_id)
    lane = Lane(seed=seed, model=model, gateway=gateway, now=now, new_id=new_id, **adapters)
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
    cause = lane.approvals[decision.approval_id]["cause"]
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


def on_signal(lane: Lane, envelope: Envelope) -> None:
    """S3: route to a task, or to tasks.unrouted for the Escalations queue."""
    signal = Signal.model_validate(envelope.payload)
    lane.signals[signal.signal_id] = signal
    task = stages_route.route(signal, lane.seed["resolver_rules"], lane.new_id, lane.now)
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
    if run.verdict.route == "execute":
        return run_steps.act_and_finish(lane, run, None)
    if run.verdict.route != "approval_required":
        return run_steps.close_without_acting(lane, run)
    paused = run_steps.open_approval(lane, run)
    lane.pending[paused.approval_id] = paused


def on_decision(lane: Lane, envelope: Envelope) -> None:
    """S4 resumes the paused run for this approval."""
    approval_id = Decision.model_validate(envelope.payload).approval_id
    if lane.runner is not None:
        return lane.runner.send_decision(lane.approvals[approval_id]["task_id"], envelope)
    run_steps.resume_after_decision(lane, lane.pending.pop(approval_id), envelope)
