# tools.py: the Lane A tool registry. Each tool has a strict argument schema, an action type, and a money flag.
# Used by: stages_reason.py (S6 offers and checks tools), S9 later (side effects, rate limits). Uses: contracts_signal.py.
from typing import Literal

from pydantic import BaseModel, Field

from app.pipeline.contracts_signal import Money

# Config
MAX_RATIONALE_CHARS = 600
REASON_CODES = Literal["within_window_full", "within_window_partial", "outside_window", "project_closed_full", "duplicate_charge", "other"]


class ToolCall(BaseModel):
    """Fields every tool call carries, so S7 and the run history can see why."""
    rationale_summary: str = Field(max_length=MAX_RATIONALE_CHARS, description="One or two plain sentences on why")
    citations: list[str] = Field(description="Ids of the documents relied on")
    confidence: float = Field(ge=0, le=1, description="How sure, from 0 to 1")


class RefundArgs(ToolCall):
    payment_ref: str = Field(pattern=r"^pay_[A-Za-z]+_\d{8}_\d{4}$", description="The payment to refund, e.g. pay_FB_20261004_0192")
    amount: Money = Field(description="Amount in minor units: LKR 12,000 is amount_minor 1200000")
    reason_code: REASON_CODES


class ReplyArgs(ToolCall):
    message_plain: str = Field(max_length=2000, description="The reply to send to the customer")


class EscalateArgs(ToolCall):
    reason: str = Field(max_length=200, description="What is missing or unclear, for the human who takes over")


TOOLS = {
    "issue_refund": {
        "tool_id": "tool_payment_refund", "version": 1, "args": RefundArgs, "touches_money": True,
        "description": "Refund a customer's payment, fully or in part, to the original payment method.",
    },
    "reply_customer": {
        "tool_id": "tool_reply_email", "version": 1, "args": ReplyArgs, "touches_money": False,
        "description": "Send the customer a written reply.",
    },
    "escalate": {
        "tool_id": "tool_escalate", "version": 1, "args": EscalateArgs, "touches_money": False,
        "description": "Hand the case to a human when information is missing, unclear, or outside the skill.",
    },
}
CALL_FIELDS = set(ToolCall.model_fields)  # kept out of the action's own arguments


def tool_schemas(names: list[str]) -> list[dict]:
    """The tools in the shape the Claude API expects."""
    return [{"name": name, "description": TOOLS[name]["description"], "input_schema": TOOLS[name]["args"].model_json_schema()} for name in names]
