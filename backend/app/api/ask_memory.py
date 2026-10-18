# ask_memory.py: Ask the Brain conversations. Each turn is appended to the record of its conversation, so the brain can
# use what was said earlier, and the console can show it again after a reload. Only the person who started it may read it.
# Used by: ask.py, routes.py. Uses: the lane's append-only records (memory or Postgres).
from datetime import datetime

from pydantic import BaseModel

from app.api.ui_models_work import AskTurn

# Config
KIND = "ask_turn"
TURNS_GIVEN_TO_CLAUDE = 12  # the latest turns go in whole; older ones stay stored and shown


class NotYourConversation(Exception):
    """Someone asked to read or continue a conversation another person started."""


class StoredTurn(BaseModel):
    conversation_id: str
    persona: str
    question: str
    answer: str
    cited: list[str]
    at: datetime


def turns(lane, conversation_id: str, persona: str) -> list[dict]:
    """Every turn of this person's conversation, oldest first. Unknown ids are simply empty."""
    stored = lane.records.history(KIND, conversation_id)
    if any(turn["persona"] != persona for turn in stored):
        raise NotYourConversation()
    return stored


def recent(lane, conversation_id: str, persona: str) -> list[tuple[str, str]]:
    """The latest turns as (question, answer) pairs, for Claude."""
    return [(turn["question"], turn["answer"]) for turn in turns(lane, conversation_id, persona)[-TURNS_GIVEN_TO_CLAUDE:]]


def remember(lane, conversation_id: str, persona: str, question: str, answer: str, cited: list[str]) -> None:
    lane.records.save(KIND, conversation_id, StoredTurn(conversation_id=conversation_id, persona=persona, question=question, answer=answer, cited=cited, at=lane.now))


def shown(lane, conversation_id: str, persona: str) -> list[dict]:
    """The console's view of the conversation."""
    return [AskTurn(question=turn["question"], answer=turn["answer"], at=str(turn["at"])).ui() for turn in turns(lane, conversation_id, persona)]
