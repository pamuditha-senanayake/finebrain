# contracts_failure.py: the DeadLetter message every {topic}.dlq carries.
# Used by: scripts/check_golden.py. Uses: contracts_signal.py.
# Source of truth: Docs/CB_System_Reference.md sections 7 and 8.
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.pipeline.contracts_signal import Envelope

# Config: stage names, so Sensors health can group failures by stage
Stage = Literal[
    "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8",
    "S9", "S10", "S11", "S12", "S13", "S14", "S15",
]


# --- DeadLetter (any consumer to its {topic}.dlq)

class DeadLetter(BaseModel):
    original: Envelope  # kept whole, so a fix can replay it with the same event_id
    consumer_group: str
    stage: Stage
    error_code: str  # stable code like parse_error, for grouping in Fleet errors
    error_message: str  # no personal data
    retryable: bool
    attempts: int = Field(ge=1)
    failed_at: datetime
