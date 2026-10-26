# stages_orchestrate.py: S4 Orchestrate, the start of a run. The Planner reads the message and picks the recipe from the
# library at the version S3 pinned; the Chat agent hands the chat to the task's agent. Out: RunStarted on runs.started.
# A later message on a chat whose run is still open (Anna's "yes, that one") joins that run instead: RunContinued on runs.continued.
# Used by: run_steps.py (start_run, in-process and on Temporal), run_approvals.py, tests. Uses: stages_orchestrate_chat.py,
# contracts_start.py, stages_record.py, stages_normalize.py (claim), observe.py.
# Plain code, no model: S3 already chose the recipe, so S4 checks it exists and pins it.
from app.pipeline import stages_orchestrate_chat as chat
from app.pipeline import stages_record
from app.pipeline.contracts_run import RunStep
from app.pipeline.contracts_signal import Envelope, Principal, Signal, TaskRequest
from app.pipeline.contracts_start import Handoff, Recipe, RunContinued, RunStarted
from app.pipeline.observe import count, log_event, log_seam
from app.pipeline.stages_normalize import claim

# Config
CHAT_AGENT_ID = "agent_chat"  # talks with the customer until a task's agent takes over
PLAN = ["S5 Retrieve", "S6 Reason", "S7 Govern", "S8 Decide", "S9 Act", "S10 Record"]
STARTED_KIND = "run_started"  # records kind keyed by task id: survives a restart, unlike the claim key


# --- Reading what the task points at

def signal_of(lane, signal_id: str) -> Signal | None:
    """The masked signal, from this process's memory or from records (when another worker routed it)."""
    if signal_id in lane.signals:
        return lane.signals[signal_id]
    stored = lane.records.load("signal", signal_id)
    return Signal.model_validate(stored) if stored else None


def principal_of(lane, agent_id: str) -> Principal | None:
    """The agent as Workflow Studio last saved it in the graph, so an edit to its rights counts on the next run."""
    found = next((node for node in lane.graph.latest("agent") if node["_ref"]["id"] == agent_id), None)
    return Principal.model_validate(found) if found else None


def why_not_startable(lane, task: TaskRequest, signal: Signal | None, skill: dict | None) -> str | None:
    """The reason S4 cannot start this task, or None when it can."""
    if signal is None:
        return "signal_missing"
    if principal_of(lane, task.agent_id) is None:
        return "agent_unknown"
    if not skill or not skill.get("allowed_tools") or not skill.get("steps"):
        return "recipe_missing"
    return None


def already_handled(lane, task_id: str) -> bool:
    """True when this task already started or joined a run. The claim is atomic across workers; the record survives restarts."""
    if not claim(lane.seen_keys, f"{lane.seed['tenant_id']}:s4:task:{task_id}"):
        return True
    try:
        return lane.records.load(STARTED_KIND, task_id) is not None or bool(lane.records.load("run_joined", task_id))
    except Exception as error:  # an outage reads as new: the claim above still stops a second worker
        log_event("S4", "start_marker_unreadable", task_id=task_id, error=type(error).__name__)
        return False


def release(lane, task_id: str) -> None:
    """Undo the task claim after a crash, so the bus can deliver the task again (as S2 does with its dedup claim)."""
    lane.seen_keys.discard(f"{lane.seed['tenant_id']}:s4:task:{task_id}")


def remember(lane, kind: str, handled: RunStarted | RunContinued) -> None:
    """Best effort, like S3's keep_signal: a records outage must not stop a run the worker can still do."""
    try:
        lane.records.save(kind, handled.task_id, handled)
    except Exception as error:
        count("s4.start_not_saved")
        log_event("S4", "start_not_saved", task_id=handled.task_id, error=type(error).__name__)


# --- Planner and hand-off

def pick_recipe(task: TaskRequest, skill: dict) -> Recipe:
    """The Planner takes the recipe at the pinned version, so a release mid run cannot change it."""
    return Recipe(skill_ref=task.skill_ref, name=skill["name"], allowed_tools=skill["allowed_tools"], steps=skill["steps"])


def hand_off(lane, task: TaskRequest, signal: Signal, run_id: str) -> Handoff | None:
    """The Chat agent passes the customer and the chat to the task's agent. Email and uploads have no chat to pass."""
    if signal.conversation_id is None:
        return None
    return Handoff(handoff_id=f"{run_id}:handoff", from_agent=CHAT_AGENT_ID, to_agent=task.agent_id, customer_ref=signal.actor.ref,
                   conversation_id=signal.conversation_id, transcript_signal_ids=chat.chat_so_far(lane, signal))


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
    task = TaskRequest.model_validate(envelope.payload)
    if already_handled(lane, task.task_id):
        count("s4.duplicate_task")
        log_event("S4", "duplicate_task", task_id=task.task_id)
        return None
    try:
        return start_or_join(lane, envelope, task)
    except Exception:
        release(lane, task.task_id)  # the bus redelivers it; nothing was published for it
        raise


def start_or_join(lane, envelope: Envelope, task: TaskRequest) -> RunStarted | None:
    # Step 1: the Planner reads the message and looks up the pinned recipe and the agent
    signal = signal_of(lane, task.signal_ids[0])
    skill = lane.graph.at_version("skill", task.skill_ref.id, task.skill_ref.version)
    reason = why_not_startable(lane, task, signal, skill)
    if reason:
        return refuse(lane, envelope, task, reason)

    # Step 2: on a chat, a later message joins the open run; of two workers starting one at once, only one wins
    conversation = signal.conversation_id
    target = chat.open_run(lane, conversation, task.agent_id) if conversation else None
    won = chat.claim_start(lane, conversation, task.agent_id) if conversation and target is None else None
    if conversation and target is None and won is None:
        target = chat.wait_for_open_run(lane, conversation, task.agent_id)
    if target is not None:
        remember(lane, "run_joined", chat.join_run(lane, envelope, task, signal, target))
        return None
    try:
        return start(lane, envelope, task, signal, skill)
    except Exception:
        chat.release_start(lane, won)
        raise


def start(lane, envelope: Envelope, task: TaskRequest, signal: Signal, skill: dict) -> RunStarted:
    """Start the run with the recipe, the plan and the chat handed to the task's agent, then tell S5."""
    # Step 1: build RunStarted
    run_id = lane.new_id("run")
    started = RunStarted(run_id=run_id, task_id=task.task_id, signal_id=signal.signal_id, agent_id=task.agent_id, request_text=signal.text_masked or "",
                         recipe=pick_recipe(task, skill), plan=PLAN, handoff=hand_off(lane, task, signal, run_id))

    # Step 2: tell S5 first, so a failed publish leaves no trace and the redelivery starts clean; then remember and index it
    lane.bus.publish("runs.started", "run.started", started, "worker", envelope)
    remember(lane, STARTED_KIND, started)
    if signal.conversation_id:
        chat.remember_run(lane, run_id, task, signal.conversation_id)
    log_seam("S4", task.model_dump(mode="json"), started.model_dump(mode="json"))
    return started
