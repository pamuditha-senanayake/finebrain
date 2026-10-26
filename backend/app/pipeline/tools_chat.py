# tools_chat.py: S9's reply runner. A reply goes back into the chat the customer wrote from: S2 scoped the run's conversation
# as "<connection>:<their conversation id>", so the live connection is read by its key and its "reply" action sends it.
# Once per key: a short claim keeps a second worker from posting at the same moment (a crash frees it when it expires),
# and a retry after an unclear failure (no answer, a 5xx) first reads the conversation for this text sent since the first
# try, so a reply that did land is never posted twice, and an earlier identical reply is never mistaken for it. Used by: run_finish.py (S9's runner for reply_customer). Uses: conn_call.py, conn_spec.py, stages_normalize.py, stages_orchestrate.py.
import re
from datetime import datetime, timedelta, timezone

from app.pipeline.conn_call import CallFailed, Connection, call, load
from app.pipeline.conn_spec import pick
from app.pipeline.observe import count, log_event
from app.pipeline.stages_normalize import claim
from app.pipeline.stages_orchestrate import signal_of

# Config
REPLY, READ = "reply", "conversation"  # the connection's actions: send a message, read one conversation
ASSISTANT_NAME = "Finebase assistant"  # the sender name the customer sees, unless the tenant sets assistant_name
SENT = "reply sent into the chat"
FRACTION = re.compile(r"\.(\d{1,6})\d*")  # Postgres drops trailing zeros (.33838); Python 3.10 reads only 3 or 6 digits
CLOCK_MARGIN = timedelta(seconds=30)  # the chat's clock and ours may differ a little; an earlier identical reply is minutes older


def failed(code: str, retryable: bool) -> dict:
    return {"status": "failed", "external_ref": None, "summary": "", "error": {"code": code, "retryable": retryable}}


def destination(lane, run) -> tuple[Connection, str] | None:
    """The live connection and its own conversation id for this run's latest message, when that chat can be answered."""
    return destination_for(lane, signal_of(lane, run.task.signal_ids[-1]))


def destination_for(lane, signal) -> tuple[Connection, str] | None:
    """The same for one message: where a reply to it goes, or None (email, uploads, a chat with no way back)."""
    if signal is None or not signal.conversation_id:
        return None
    connection_id, _, conversation = signal.conversation_id.partition(":")
    connection = load(lane, connection_id)
    if connection is None or connection.status != "live" or connection.manifest is None or REPLY not in connection.manifest.actions:
        return None
    return connection, conversation


# --- Talking to the chat

def post(lane, connection: Connection, conversation: str, text: str) -> dict:
    """Send the reply and return the chat's own id for it. A site whose reply action names no body gets the text under the
    name its own feed gives a message's text (finebaselabs.com: "body"), so its answer need not spell out a template."""
    values = {"conversation_id": conversation, "text": text, "agent_name": lane.seed.get("assistant_name", ASSISTANT_NAME), "buttons": []}
    feed = connection.manifest.inbound
    answer = call(lane, connection, REPLY, values, default_body={(feed.fields.get("text", "text") if feed else "text"): text})
    ref = pick(answer, "id") or pick(answer, "message.id")
    return {"status": "succeeded", "external_ref": str(ref) if ref else None, "summary": SENT}


def read_time(text: str) -> datetime:
    """A chat's timestamp, whatever number of fraction digits or Z it uses."""
    return datetime.fromisoformat(FRACTION.sub(lambda m: "." + m.group(1).ljust(6, "0"), text.replace("Z", "+00:00"), count=1))


def sent_since(message: dict, created_field: str, first_try: datetime) -> bool:
    """True when the chat stored the message after our first try. A chat that gives no time is taken at its word."""
    created = pick(message, created_field)
    return not created or read_time(str(created)) >= first_try - CLOCK_MARGIN


def already_posted(lane, connection: Connection, conversation: str, text: str, first_try: datetime) -> dict | None:
    """The brain's message with this exact text, sent since the first try, if one landed. None when the chat cannot be read."""
    feed = connection.manifest.inbound
    if READ not in connection.manifest.actions or feed is None:
        return None
    read = call(lane, connection, READ, {"conversation_id": conversation})
    messages = read.get(feed.items_field) or read.get("messages") or []  # a site may list a conversation's messages under its own name
    sender, body = feed.fields.get("sender", "sender"), feed.fields.get("text", "body")
    created = feed.fields.get("created_at", "created_at")
    found = next((m for m in messages if pick(m, sender) != feed.only_sender and pick(m, body) == text and sent_since(m, created, first_try)), None)
    return {"status": "succeeded", "external_ref": str(pick(found, feed.fields.get("message_id", "id"))), "summary": SENT} if found else None


def unclear(error: CallFailed) -> bool:
    """No answer, a server error or a rate limit: the reply may or may not have landed, and trying again can help."""
    return error.status is None or error.status >= 500 or error.status == 429


# --- The reply tool

def send(lane, connection: Connection, conversation: str, arguments: dict, key: str) -> dict:
    """S9's call: one reply, once."""
    claims, tried, text = lane.tooling["claims"], lane.tooling["tried"], arguments["message_plain"]
    # Step 1: one worker per key; the other gets the stored answer, or tries again shortly
    if not claim(claims, key):
        stored = lane.tooling["results"].get(key)
        return {"status": "succeeded", "external_ref": stored["external_ref"], "summary": stored["response_summary"]} if stored else failed("reply_in_flight", True)
    try:
        # Step 2: tried before with an unclear outcome? Look for it since that try before posting again
        first = tried.get(key)
        if first and (landed := already_posted(lane, connection, conversation, text, datetime.fromisoformat(first["at"]))):
            count("s9.reply_found_landed")
            return landed
        if not first:
            tried.put(key, {"at": datetime.now(timezone.utc).isoformat()})  # the wall clock, as the chat stamps its messages
        return post(lane, connection, conversation, text)
    except CallFailed as error:
        count(f"s9.reply_failed.{connection.connection_id}")
        log_event("S9", "reply_failed", connection_id=connection.connection_id, status=error.status)
        return failed("chat_unavailable", True) if unclear(error) else failed("chat_refused", False)
    finally:
        claims.discard(key)


def runner(lane, run):
    """S9's runner for replies in this run: the customer's own chat. Without one, a lane built with a stand-in sender (stage
    tests) uses it; production has none, so the reply fails and a person answers instead."""
    def run_reply(tool_id: str, arguments: dict, key: str) -> dict:
        where = destination(lane, run)
        if where:
            return send(lane, *where, arguments, key)
        sender = lane.tooling.get("send_email")
        return sender(tool_id, arguments, key) if sender else failed("no_reply_channel", False)
    return run_reply
