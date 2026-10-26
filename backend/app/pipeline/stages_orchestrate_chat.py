# stages_orchestrate_chat.py: S4's chat side. One chat reaches S4 many times, so S4 keeps per conversation the messages
# in order and the runs it started, as versions of one record each: finding the chat so far or the open run is one read,
# never a scan. It claims a conversation atomically so two workers never start two runs, and delivers a later message
# to the run that is still open. Used by: stages_orchestrate.py, orchestrate.py (the S3 consumer). Uses: contracts_start.py,
# stages_normalize.py (claim), retry.py, observe.py, a records store, a key set and, on Temporal, the runner.
from app.pipeline.contracts_signal import Envelope, Signal, TaskRequest
from app.pipeline.contracts_start import ConversationMessage, OpenRun, RunContinued
from app.pipeline.observe import count, log_event, log_seam
from app.pipeline.retry import call_with_retry
from app.pipeline.stages_normalize import claim
from app.pipeline.stages_route import task_id_for

# Config
MESSAGES_KIND = "conversation_message"  # keyed by conversation id; one version per message
RUNS_KIND = "conversation_run"  # keyed by conversation id; one version per run started on it
INBOX_KIND = "run_inbox"  # keyed by run id; one version per later message delivered to that run
CLOSED_OUTCOMES = {"resolved", "escalated", "failed", "blocked", "abandoned"}  # awaiting_approval is still open
CONTINUES_FLAG = "continues_open_run"  # on a K3 built for a follow-up that no rule matched
WAIT_ATTEMPTS, WAIT_DELAY = 5, 0.1  # a worker that lost the start claim waits up to about 3 s for the winner's run


class ConversationBusy(Exception):
    """Another worker is starting this conversation's run right now. The bus delivers the task again."""
    retryable = True


# --- The chat so far

def remember_message(lane, signal: Signal) -> None:
    """Called by the S3 consumer for every chat message, routed or not, so the agent later sees the whole chat."""
    if signal.conversation_id is None:
        return
    try:
        lane.records.save(MESSAGES_KIND, signal.conversation_id, ConversationMessage(signal_id=signal.signal_id, at=lane.now))
    except Exception as error:  # the run can still go ahead with fewer messages in its hand-off
        count("s4.message_not_saved")
        log_event("S4", "message_not_saved", signal_id=signal.signal_id, error=type(error).__name__)


def chat_so_far(lane, signal: Signal) -> list[str]:
    """Every message on this chat up to and including this one, oldest first. An outage hands over this message alone."""
    try:
        stored = [version["signal_id"] for version in lane.records.history(MESSAGES_KIND, signal.conversation_id)]
    except Exception as error:
        log_event("S4", "chat_unreadable", signal_id=signal.signal_id, error=type(error).__name__)
        stored = []
    ids = list(dict.fromkeys(stored))  # a redelivered message is listed once
    if signal.signal_id not in ids:
        return ids + [signal.signal_id]
    return ids[: ids.index(signal.signal_id) + 1]


# --- Runs on a conversation

def run_closed(lane, run_id: str) -> bool:
    """True once S10 recorded a final outcome. A run waiting for approval is still open."""
    record = lane.records.load("run", run_id)
    return record is not None and record["outcome"] in CLOSED_OUTCOMES


def open_run(lane, conversation_id: str, agent_id: str | None = None) -> OpenRun | None:
    """The newest run still open on this chat, for this agent or any agent. An outage reads as none: a new run starts."""
    try:
        runs = [OpenRun.model_validate(version) for version in lane.records.history(RUNS_KIND, conversation_id)]
        mine = [run for run in runs if agent_id is None or run.task.agent_id == agent_id]
        return next((run for run in reversed(mine) if not run_closed(lane, run.run_id)), None)
    except Exception as error:
        log_event("S4", "open_runs_unreadable", conversation_id=conversation_id, error=type(error).__name__)
        return None


def claim_start(lane, conversation_id: str, agent_id: str) -> str | None:
    """Atomic (Valkey SET NX in production): of two workers starting a run on one chat at once, exactly one wins and
    gets the key back. The key counts this agent's runs on the chat, so after a run closes the next one can be claimed."""
    try:
        started = sum(1 for version in lane.records.history(RUNS_KIND, conversation_id) if version["task"]["agent_id"] == agent_id)
    except Exception:
        started = 0
    key = f"{lane.seed['tenant_id']}:s4:start:{conversation_id}:{agent_id}:{started}"
    return key if claim(lane.seen_keys, key) else None


def release_start(lane, key: str | None) -> None:
    """The winner crashed before its run was saved: free the chat, or every later message would wait for a run that never comes."""
    if key is not None:
        lane.seen_keys.discard(key)


def wait_for_open_run(lane, conversation_id: str, agent_id: str) -> OpenRun:
    """The worker that lost the claim waits for the winner's run, then joins it. Still nothing: the bus retries later."""
    def look() -> OpenRun:
        found = open_run(lane, conversation_id, agent_id)
        if found is None:
            raise ConversationBusy(conversation_id)
        return found

    return call_with_retry(look, lambda error: isinstance(error, ConversationBusy), attempts=WAIT_ATTEMPTS, base_delay=WAIT_DELAY)


def remember_run(lane, run_id: str, task: TaskRequest, conversation_id: str) -> None:
    """Best effort, like S3's keep_signal: a records outage must not stop a run the worker can still do."""
    try:
        lane.records.save(RUNS_KIND, conversation_id, OpenRun(run_id=run_id, task=task))
    except Exception as error:
        count("s4.run_not_indexed")
        log_event("S4", "run_not_indexed", run_id=run_id, error=type(error).__name__)


# --- Joining an open run

def join_run(lane, envelope: Envelope, task: TaskRequest, signal: Signal, target: OpenRun) -> RunContinued:
    """A later message joins the open run: no new recipe pick, no second hand-off. It lands in the run's inbox, which
    any worker can read, and on Temporal it also reaches the running workflow as a signal."""
    joined = RunContinued(run_id=target.run_id, task_id=task.task_id, signal_id=signal.signal_id, agent_id=task.agent_id,
                          request_text=signal.text_masked or "", transcript_signal_ids=chat_so_far(lane, signal))
    lane.records.save(INBOX_KIND, target.run_id, joined)  # not best effort: this is the delivery, so a failure is retried
    sent = lane.bus.publish("runs.continued", "run.continued", joined, "worker", envelope)
    signal_workflow(lane, target.task.task_id, sent)
    log_seam("S4", task.model_dump(mode="json"), joined.model_dump(mode="json"))
    count("s4.joined")
    return joined


def signal_workflow(lane, task_id: str, sent: Envelope) -> None:
    """On Temporal, hand the message to the run's workflow. A workflow that already ended keeps it in the inbox only."""
    if lane.runner is None:
        return
    try:
        lane.runner.send_message(task_id, sent)
    except Exception as error:
        count("s4.workflow_not_signalled")
        log_event("S4", "workflow_not_signalled", task_id=task_id, error=type(error).__name__)


def inbox(lane, run_id: str) -> list[RunContinued]:
    """The later messages delivered to a run, oldest first: what S6 reads when the run goes on."""
    delivered = [RunContinued.model_validate(version) for version in lane.records.history(INBOX_KIND, run_id)]
    return list({message.task_id: message for message in delivered}.values())  # a message delivered twice after a crash counts once


# --- Follow-ups no rule matches

def continuation_task(lane, signal: Signal) -> TaskRequest | None:
    """"yes, that one" matches no routing rule, but its chat has an open run: S3 hands it on as a K3 for that run's
    skill and agent, flagged, instead of sending it to Escalations. None when the chat has no open run."""
    if signal.conversation_id is None:
        return None
    target = open_run(lane, signal.conversation_id)
    if target is None:
        return None
    count("s3.continued_open_run")
    return target.task.model_copy(update={"task_id": task_id_for(signal), "signal_ids": [signal.signal_id], "flags": [*signal.flags, CONTINUES_FLAG]})
