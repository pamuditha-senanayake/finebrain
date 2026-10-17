# recorder.py: the S10 recorder consumer. Saves approvals, decisions, action results and run records.
# Used by: orchestrate.py. Uses: contracts_run.py, a records store (store_memory.py or store_postgres.py).
from pydantic import BaseModel

from app.pipeline.contracts_run import ActionResult, ApprovalRequest, Decision, RunRecord

# Config: topic to (record kind, contract, id field)
RECORDED_TOPICS = {
    "approvals.requested": ("approval", ApprovalRequest, "approval_id"),
    "approvals.decided": ("decision", Decision, "approval_id"),
    "actions.executed": ("action", ActionResult, "action_id"),
    "runs.completed": ("run", RunRecord, "run_id"),
}


def make_saver(records, kind: str, contract: type[BaseModel], id_field: str):
    """A handler that validates one payload and appends it as a new version."""

    def save(envelope) -> None:
        body = contract.model_validate(envelope.payload)
        records.save(kind, getattr(body, id_field), body)

    return save


def subscribe_recorder(bus, records) -> None:
    """One recorder consumer group across the topics worth keeping."""
    for topic, (kind, contract, id_field) in RECORDED_TOPICS.items():
        bus.subscribe(topic, "recorder", "S10", make_saver(records, kind, contract, id_field))
