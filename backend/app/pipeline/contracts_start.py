# contracts_start.py: Pydantic models for the S4 seam (K3 TaskRequest in; RunStarted on runs.started, or RunContinued on runs.continued).
# Used by: stages_orchestrate.py, tests/test_s4_orchestrate_bdd.py. Uses: contracts_signal.py.
# S5 reads RunStarted to know the run id, the recipe the Planner picked, and the chat the Refund agent was handed.
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.pipeline.contracts_signal import TaskRequest, VersionRef

# Config: enum values
StageName = Literal["S5 Retrieve", "S6 Reason", "S7 Govern", "S8 Decide", "S9 Act", "S10 Record"]


class Recipe(BaseModel):
    """The skill the Planner picked from the library, at the version S3 pinned."""
    skill_ref: VersionRef
    name: str
    allowed_tools: list[str] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)


class Handoff(BaseModel):
    """The Chat agent passes the conversation to the task's agent, with the customer and chat attached."""
    handoff_id: str
    from_agent: str
    to_agent: str
    customer_ref: str  # a PiiToken for people, never the raw name
    conversation_id: str  # the chat session (K2 conversation_id); unique within a tenant
    transcript_signal_ids: list[str] = Field(min_length=1)  # oldest first, ending with this task's message


class RunStarted(BaseModel):
    run_id: str
    task_id: str
    signal_id: str
    agent_id: str
    request_text: str  # the masked message the Planner read
    recipe: Recipe
    plan: list[StageName]
    handoff: Handoff | None  # None when the signal is not a chat (email, upload)


class RunContinued(BaseModel):
    """A later message on a chat whose run is still open: it joins that run, with no new recipe pick and no new handoff."""
    run_id: str  # the open run this message joins
    task_id: str
    signal_id: str
    agent_id: str
    request_text: str
    transcript_signal_ids: list[str] = Field(min_length=1)  # the chat so far, ending with this message


class OpenRun(BaseModel):
    """One run S4 started on a conversation. Versions of one record per conversation, so finding the open run is one read."""
    run_id: str
    task: TaskRequest  # kept whole, so a follow-up S3 cannot route can still join this run with the same skill and agent


class ConversationMessage(BaseModel):
    """One message on a conversation, in arrival order. The versions of one record are the chat so far."""
    signal_id: str
    at: datetime | None = None  # when the brain received it; optional so old records validate


class ConversationReply(BaseModel):
    """One message the brain's side sent into a conversation: the agent's reply, a notice, or a person's."""
    text: str
    by: Literal["agent", "system", "human"]
    author: str  # the agent id, "system", or the person
    run_id: str | None = None
    at: datetime
    after: str | None = None  # the customer message it answers, so the chat reads in order whatever the clocks say


class ConversationState(BaseModel):
    """Who has the conversation: its agent, a person who took it over, or nobody once it is closed."""
    status: Literal["agent", "human", "closed"]
    by: str
    at: datetime
    note: str = ""
