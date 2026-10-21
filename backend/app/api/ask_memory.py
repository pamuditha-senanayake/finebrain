# ask_memory.py: Ask the Brain conversations. Each turn is appended to the record of its conversation, so the brain can
# use what was said earlier, and the console can show it again after a reload. Only the person who started it may read it.
# Used by: ask.py, routes.py. Uses: the lane's append-only records (memory or Postgres).
from datetime import datetime

from pydantic import BaseModel

from app.api.ui_models_work import AskConversation, AskTurn

# Config
KIND = "ask_turn"
TURNS_GIVEN_TO_CLAUDE = 12  # the latest turns go in whole; older ones stay stored and shown
CONVERSATIONS_SHOWN = 30  # the history lists this many, newest first
TITLE_WORDS = 7


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


def title_of(question: str) -> str:
    """The first question, cut to a few words, names the chat."""
    words = question.split()
    return " ".join(words[:TITLE_WORDS]) + ("…" if len(words) > TITLE_WORDS else "")


def conversations(lane, persona: str) -> list[dict]:
    """This person's chats for the history, newest first. Each record's latest version is its last turn."""
    last_turns = [turn for turn in lane.records.list_kind(KIND) if turn["persona"] == persona]
    newest = sorted(last_turns, key=lambda turn: str(turn["at"]), reverse=True)[:CONVERSATIONS_SHOWN]
    listed = []
    for last in newest:
        every = lane.records.history(KIND, last["conversation_id"])
        listed.append(AskConversation(id=last["conversation_id"], title=title_of(every[0]["question"]), at=str(last["at"]), turns=len(every)).ui())
    return listed


def serve(lane, resource: str, params, persona: str) -> list[dict]:
    """GET ask/turns (one chat) and ask/conversations (the history)."""
    if resource == "ask/conversations":
        return conversations(lane, persona)
    return shown(lane, params.get("conversation", ""), persona)


def shown(lane, conversation_id: str, persona: str) -> list[dict]:
    """The console's view of the conversation."""
    return [AskTurn(question=turn["question"], answer=turn["answer"], at=str(turn["at"])).ui() for turn in turns(lane, conversation_id, persona)]
