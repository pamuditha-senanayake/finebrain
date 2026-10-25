# stages_orchestrate.py: S4 Orchestrate, the start of a run. The Planner reads the message and picks the recipe from the
# library at the version S3 pinned; the Chat agent hands the chat to the task's agent. Out: RunStarted on runs.started.
# A later message on a chat whose run is still open (Amara's "yes, that one") joins that run instead: RunContinued on runs.continued.
# Used by: run_steps.py (start_run, both in-process and on Temporal), tests. Uses: contracts_start.py, stages_record.py, observe.py.
# Plain code, no model: with one recipe per activity there is nothing for a model to choose.
from app.pipeline import stages_record
from app.pipeline.contracts_run import RunStep
from app.pipeline.contracts_signal import Envelope, Signal, TaskRequest
from app.pipeline.contracts_start import Handoff, Recipe, RunContinued, RunStarted
from app.pipeline.observe import count, log_event, log_seam

# Config
CHAT_AGENT_ID = "agent_chat"  # talks with the customer until a task's agent takes over
PLAN = ["S5 Retrieve", "S6 Reason", "S7 Govern", "S8 Decide", "S9 Act", "S10 Record"]
STARTED_KIND = "run_started"  # records kinds, keyed by task id, so a task delivered twice is handled once
JOINED_KIND = "run_joined"
CLOSED_OUTCOMES = {"resolved", "escalated", "failed", "blocked", "abandoned"}  # awaiting_approval is still open


# --- Reading what the task points at

def signal_of(lane, signal_id: str) -> Signal | None:
    """The masked signal, from this process's memory or from records (when another worker routed it)."""
    if signal_id in lane.signals:
        return lane.signals[signal_id]
    stored = lane.records.load("signal", signal_id)
    return Signal.model_validate(stored) if stored else None


def why_not_startable(lane, task: TaskRequest, signal: Signal | None, skill: dict | None) -> str | None:
    """The reason S4 cannot start this task, or None when it can."""
    if signal is None:
        return "signal_missing"
    if task.agent_id not in lane.seed["agents"]:
        return "agent_unknown"
    if not skill or not skill.get("allowed_tools") or not skill.get("steps"):
        return "recipe_missing"
    return None


def already_handled(lane, task_id: str) -> bool:
    """True when this task already started or joined a run. A records outage reads as False: the bus still drops exact redeliveries."""
    try:
        return any(lane.records.load(kind, task_id) is not None for kind in (STARTED_KIND, JOINED_KIND))
    except Exception as error:
        log_event("S4", "start_marker_unreadable", task_id=task_id, error=type(error).__name__)
        return False


def remember(lane, kind: str, handled: RunStarted | RunContinued) -> None:
    """Best effort, like S3's keep_signal: a records outage must not stop a run the worker can still do."""
    try:
        lane.records.save(kind, handled.task_id, handled)
    except Exception as error:
        count("s4.start_not_saved")
        log_event("S4", "start_not_saved", task_id=handled.task_id, error=type(error).__name__)


def run_closed(lane, run_id: str) -> bool:
    """True once S10 recorded a final outcome. A run waiting for approval is still open."""
    record = lane.records.load("run", run_id)
    return record is not None and record["outcome"] in CLOSED_OUTCOMES


def open_run_on_chat(lane, signal: Signal, agent_id: str) -> dict | None:
    """The newest run this agent still has open on this chat, or None. Email and uploads have no chat, so never join."""
    if signal.thread_ref is None:
        return None
    try:
        on_chat = [run for run in lane.records.list_kind(STARTED_KIND) if run["agent_id"] == agent_id and (run["handoff"] or {}).get("thread_ref") == signal.thread_ref]
        return next((run for run in reversed(on_chat) if not run_closed(lane, run["run_id"])), None)
    except Exception as error:  # an outage starts a new run rather than losing the message
        log_event("S4", "open_runs_unreadable", signal_id=signal.signal_id, error=type(error).__name__)
        return None


# --- Planner and handoff

def pick_recipe(task: TaskRequest, skill: dict) -> Recipe:
    """The Planner takes the recipe at the pinned version, so a release mid run cannot change it."""
    return Recipe(skill_ref=task.skill_ref, name=skill["name"], allowed_tools=skill["allowed_tools"], steps=skill["steps"])


def chat_so_far(lane, signal: Signal) -> list[str]:
    """Every message on this chat up to and including this one, oldest first. Read from records so any worker sees it.
    A records outage hands over this message alone, rather than stopping the run."""
    try:
        on_thread = [stored["signal_id"] for stored in lane.records.list_kind("signal") if stored.get("thread_ref") == signal.thread_ref]
    except Exception as error:
        log_event("S4", "chat_unreadable", signal_id=signal.signal_id, error=type(error).__name__)
        on_thread = []
    if signal.signal_id not in on_thread:
        return on_thread + [signal.signal_id]
    return on_thread[: on_thread.index(signal.signal_id) + 1]


def hand_off(lane, task: TaskRequest, signal: Signal, run_id: str) -> Handoff | None:
    """The Chat agent passes the customer and the chat to the task's agent. Email and uploads have no chat to pass."""
    if signal.thread_ref is None:
        return None
    return Handoff(handoff_id=f"{run_id}:handoff", from_agent=CHAT_AGENT_ID, to_agent=task.agent_id, customer_ref=signal.actor.ref,
                   thread_ref=signal.thread_ref, transcript_signal_ids=chat_so_far(lane, signal))


def join_run(lane, envelope: Envelope, task: TaskRequest, signal: Signal, open_run: dict) -> None:
    """A later message on the chat joins its open run: no new recipe pick and no second handoff."""
    joined = RunContinued(run_id=open_run["run_id"], task_id=task.task_id, signal_id=signal.signal_id, agent_id=task.agent_id,
                          request_text=signal.text_masked or "", transcript_signal_ids=chat_so_far(lane, signal))
    remember(lane, JOINED_KIND, joined)
    lane.bus.publish("runs.continued", "run.continued", joined, "worker", envelope)
    log_seam("S4", task.model_dump(mode="json"), joined.model_dump(mode="json"))


# --- Closing a task that cannot start

def close_escalated(lane, envelope: Envelope, task: TaskRequest, run_id: str, step: RunStep) -> None:
    """Escalate to a human with one step saying why, and act on nothing. Shared with S5's context_unavailable."""
    trace = {"task": task.model_dump(mode="json"), "steps": [step.model_dump(mode="json")], "outcome": "escalated"}
    written = stages_record.write_trace(lane.object_store, stages_record.trace_uri(lane.seed, run_id), trace)
    record, event = stages_record.record(task, None, [step], "escalated", None, lane.seed, lane.now, lane.now, run_id=run_id, trace_written=written)
    lane.bus.publish("runs.completed", "run.completed", record, "recorder", envelope)
    lane.bus.publish("ui.events", "ui.event", event, "recorder", envelope)


def refuse(lane, envelope: Envelope, task: TaskRequest, reason: str) -> None:
    """S4 cannot start the task: count it, log it, and close it as escalated."""
    count(f"s4.not_started.{reason}")
    log_event("S4", "not_started", task_id=task.task_id, reason=reason)
    step = RunStep(step_id="step_00", kind="judgment", started_at=lane.now, duration_ms=0, decision=reason, reason=f"S4 could not start: {reason}", refs=task.signal_ids)
    close_escalated(lane, envelope, task, lane.new_id("run"), step)


# --- Entry point

def begin_run(lane, envelope: Envelope) -> RunStarted | None:
    """S4: plan the run, hand the chat over, and publish RunStarted. None when it joined an open run, already ran, or cannot start."""
    # Step 1: a task delivered twice is handled once
    task = TaskRequest.model_validate(envelope.payload)
    if already_handled(lane, task.task_id):
        count("s4.duplicate_task")
        log_event("S4", "duplicate_task", task_id=task.task_id)
        return None

    # Step 2: the Planner reads the message and looks up the pinned recipe in the library
    signal = signal_of(lane, task.signal_ids[0])
    skill = lane.graph.at_version("skill", task.skill_ref.id, task.skill_ref.version)
    reason = why_not_startable(lane, task, signal, skill)
    if reason:
        return refuse(lane, envelope, task, reason)

    # Step 3: a later message on a chat whose run is still open joins that run
    open_run = open_run_on_chat(lane, signal, task.agent_id)
    if open_run is not None:
        return join_run(lane, envelope, task, signal, open_run)

    # Step 4: start the run with the recipe, the plan and the chat handed to the task's agent
    run_id = lane.new_id("run")
    started = RunStarted(run_id=run_id, task_id=task.task_id, signal_id=signal.signal_id, agent_id=task.agent_id, request_text=signal.text_masked or "",
                         recipe=pick_recipe(task, skill), plan=PLAN, handoff=hand_off(lane, task, signal, run_id))

    # Step 5: remember it, tell S5, and log the seam
    remember(lane, STARTED_KIND, started)
    lane.bus.publish("runs.started", "run.started", started, "worker", envelope)
    log_seam("S4", task.model_dump(mode="json"), started.model_dump(mode="json"))
    return started
