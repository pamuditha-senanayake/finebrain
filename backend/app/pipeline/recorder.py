# recorder.py: the S10 recorder consumer. Saves approvals, decisions, action results and run records.
# Used by: orchestrate.py. Uses: contracts_run.py, a records store (store_memory.py or store_postgres.py).
from pydantic import BaseModel

from app.pipeline.contracts_run import ActionResult, ApprovalRequest, Decision, RunRecord
from app.pipeline.observe import count, set_flag

# Config: topic to (record kind, contract, id field)
RECORDED_TOPICS = {
    "approvals.requested": ("approval", ApprovalRequest, "approval_id"),
    "approvals.decided": ("decision", Decision, "approval_id"),
    "actions.executed": ("action", ActionResult, "action_id"),
    "runs.completed": ("run", RunRecord, "run_id"),
}


class RecorderUnavailable(Exception):
    """The records store could not be written. A replay later will work."""
    retryable = True


def make_saver(records, kind: str, contract: type[BaseModel], id_field: str):
    """A handler that validates one payload and appends it as a new version."""

    def save(envelope) -> None:
        body = contract.model_validate(envelope.payload)
        try:
            records.save(kind, getattr(body, id_field), body)
        except Exception as error:  # the event stays on the bus and in the DLQ for replay; the console shows "delayed"
            count("s10.recorder_failed")
            set_flag("recorder_delayed", True)
            raise RecorderUnavailable(type(error).__name__) from None
        set_flag("recorder_delayed", False)

    return save


def subscribe_recorder(bus, records) -> None:
    """One recorder consumer group across the topics worth keeping."""
    for topic, (kind, contract, id_field) in RECORDED_TOPICS.items():
        bus.subscribe(topic, "recorder", "S10", make_saver(records, kind, contract, id_field))
