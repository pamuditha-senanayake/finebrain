# orchestrate.py: S4 Orchestrate. Wires S2, S3 and the task consumers onto a bus, given its adapters.
# Used by: tests, demos, capture_api.py. Uses: lane.py, adapters.py, run_steps.py, run_approvals.py, recorder.py, audit.py, ui_stream.py, entity_match.py, item_tags.py, stages_*.py.
# Each task runs in-process, or as a Temporal workflow when the adapters include a Temporal runner.
from datetime import datetime

from app.pipeline import entity_match, item_tags, run_approvals, run_steps, stages_extract, stages_file, stages_librarian, stages_intake, stages_normalize, stages_route, stages_version
from app.pipeline.adapters import make_memory_adapters
from app.pipeline.audit import subscribe_audit
from app.pipeline.contracts_run import Decision
from app.pipeline.contracts_signal import Envelope, RawSignalEnvelope, Signal
from app.pipeline.fakes import Gateway, Model, make_id_maker, pass_grader
from app.pipeline.lane import Lane
from app.pipeline.observe import count, log_event
from app.pipeline.recorder import subscribe_recorder
from app.pipeline.ui_stream import subscribe_broadcaster


# --- Wiring

def build_lane(seed: dict, model: Model, gateway: Gateway, now: datetime, make_adapters=make_memory_adapters, choose=None, grade=None, new_id=None,
               classify=None, extract=None) -> Lane:
    """Build the adapters, then subscribe one consumer group per stage. A live tenant passes new_id so ids stay unique across restarts."""
    new_id = new_id or make_id_maker()
    adapters = make_adapters(seed, now, new_id)
    lane = Lane(seed=seed, model=model, gateway=gateway, now=now, new_id=new_id, choose=choose or no_tie_break, grade=grade or pass_grader,
                classify=classify, extract=extract, **adapters)
    entity_match.seed_known(lane.entities, seed, now)
    lane.bus.subscribe("signals.raw", "normalizer", "S2", lambda envelope: on_raw(lane, envelope))
    lane.bus.subscribe("signals.normalized", "resolver", "S3", lambda envelope: on_signal(lane, envelope))
    lane.bus.subscribe("graph.released", "retriever", "S5", lambda envelope: stages_version.on_release(lane, envelope))
    lane.bus.subscribe("signals.normalized", "librarian", "S11", lambda envelope: stages_file.file_document(lane, Signal.model_validate(envelope.payload)))
    lane.bus.subscribe("docs.extracted", "extractor", "S11", lambda envelope: stages_extract.extract_document(lane, envelope))
    lane.bus.subscribe("facts.candidates", "reviewer", "S12", lambda envelope: stages_librarian.review_candidate(lane, envelope))
    lane.bus.subscribe("tasks.created", "worker", "S4", lambda envelope: on_task(lane, envelope))
    lane.bus.subscribe("approvals.decided", "worker", "S8", lambda envelope: on_decision(lane, envelope))
    subscribe_recorder(lane.bus, lane.records)
    subscribe_audit(lane.bus, lane.audit)
    subscribe_broadcaster(lane.bus, lane.broadcaster)
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
    """S2: normalize and tag (entities and domain), or drop silently when it is a redelivery."""
    k1 = RawSignalEnvelope.model_validate(envelope.payload)
    signal = stages_normalize.normalize(k1, envelope.event_id, lane.seed["tenant_id"], lane.object_store, lane.vault, lane.seen_keys, lane.new_id)
    if signal is None:
        return
    try:
        signal = item_tags.tag_signal(lane, signal)
    except Exception:
        lane.seen_keys.discard(signal.dedup_key)  # release the claim, so a retry or replay can run
        raise
    lane.bus.publish("signals.normalized", "signal.normalized", signal, "normalizer", envelope)


def no_tie_break(text: str, options: dict) -> None:
    """Default chooser: no model call, so a close call goes to a human."""
    return None


def keep_signal(lane: Lane, signal: Signal) -> None:
    """Save the masked signal so another worker process can read it. Best effort: this worker already holds it."""
    try:
        lane.records.save("signal", signal.signal_id, signal)
    except Exception as error:
        count("s3.signal_not_saved")
        log_event("S3", "signal_not_saved", signal_id=signal.signal_id, error=type(error).__name__)


def on_signal(lane: Lane, envelope: Envelope) -> None:
    """S3: route to a task, to tasks.unrouted for the Escalations queue, or leave documents to Lane B."""
    signal = Signal.model_validate(envelope.payload)
    lane.signals[signal.signal_id] = signal
    keep_signal(lane, signal)
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
