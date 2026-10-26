# conversation_log.py: for L3 Conversations, what the brain's side said into each chat (the agent's replies, notices, a
# person's messages) and who has the chat now (its agent, a person who took it over, or nobody once closed). Both are
# versions of one record per conversation, so reading a chat is one key read. S4 asks it before letting an agent answer.
# Used by: run_finish.py, stages_orchestrate.py, api/conversations.py. Uses: contracts_start.py, observe.py.
from app.pipeline.contracts_start import ConversationReply, ConversationState
from app.pipeline.observe import count, log_event

# Config
REPLIES_KIND = "conversation_reply"  # keyed by conversation id; one version per message the brain's side sent
STATE_KIND = "conversation_state"  # keyed by conversation id; who has the chat now


def remember_reply(lane, conversation_id: str | None, text: str, by: str, author: str, run_id: str | None = None, after: str | None = None) -> None:
    """What the brain's side said into the chat, for L3. Best effort: the message already went out, so an outage is only counted."""
    if conversation_id is None:
        return
    try:
        lane.records.save(REPLIES_KIND, conversation_id, ConversationReply(text=text, by=by, author=author, run_id=run_id, at=lane.now, after=after))
    except Exception as error:
        count("s9.reply_not_recorded")
        log_event("S9", "reply_not_recorded", conversation_id=conversation_id, error=type(error).__name__)


def taken_over(lane, conversation_id: str | None) -> bool:
    """True while a person has the chat, so no agent answers it. Read by its key. An outage reads as not taken over, as
    S4's other chat reads do, so the run is never lost; it is counted and logged."""
    try:
        state = lane.records.load(STATE_KIND, conversation_id) if conversation_id else None
    except Exception as error:
        count("s4.chat_state_unreadable")
        log_event("S4", "chat_state_unreadable", conversation_id=conversation_id, error=type(error).__name__)
        return False
    return bool(state) and state["status"] == "human"


def set_state(lane, conversation_id: str, status: str, by: str, note: str = "") -> ConversationState:
    state = ConversationState(status=status, by=by, at=lane.now, note=note)
    lane.records.save(STATE_KIND, conversation_id, state)
    return state
