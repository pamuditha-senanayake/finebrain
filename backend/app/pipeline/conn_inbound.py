# conn_inbound.py: brings a live connection's customer messages into the brain. A background loop polls each live
# connection with its cursor; a signed push lands on the same path. Every message goes through S1 (stored once, K1)
# with its conversation in the session header, so S2 gives the signal a thread.
# Used by: api/hq.py (starts the loop), api/connect_routes.py (push). Uses: conn_call.py, conn_spec.py, orchestrate.py, observe.py.
import hashlib
import hmac
import json
import threading
import time
from datetime import datetime, timezone

from app.pipeline import orchestrate
from app.pipeline.conn_call import CallFailed, Connection, all_connections, call, get_secret, load, save
from app.pipeline.conn_spec import pick
from app.pipeline.observe import count, log_event, touch

# Config
LOOP_SECONDS = 1.0
last_polled: dict[str, float] = {}  # connection id to monotonic time; in memory, so a restart polls at once


# --- One message into S1

def raw_of(connection: Connection, message: dict) -> dict:
    """The raw signal S1 stores: the brain's chat body, the message id for dedup, the conversation as the session."""
    fields = {name: pick(message, field) for name, field in connection.manifest.inbound.fields.items()}
    body = {"text": fields.get("text") or "", "customer_ref": fields.get("customer_id"),
            "visitor_name": fields.get("customer_name"), "visitor_email": fields.get("customer_email")}
    return {
        "connector_id": connection.connection_id, "grant_id": f"grant_{connection.connection_id}", "source_type": "chat",
        "external_id": str(fields.get("message_id")), "content_type": "application/json", "raw_body": json.dumps(body),
        "headers_subset": {"session": str(fields["conversation_id"])} if fields.get("conversation_id") else {},
    }


def take_in(lane, connection: Connection, messages: list[dict]) -> list[str]:
    """Capture each customer message and return the ids taken. Messages from the agent side are skipped."""
    inbound = connection.manifest.inbound
    sender = inbound.fields.get("sender")
    taken = []
    for message in messages:
        if inbound.only_sender and sender and pick(message, sender) != inbound.only_sender:
            continue
        if pick(message, inbound.fields["message_id"]) in (None, ""):
            count(f"s1.rejected.missing_external_id.{connection.connection_id}")  # without an id, dedup would merge them
            continue
        envelope = orchestrate.capture_signal(lane, raw_of(connection, message))
        taken.append(str(pick(message, inbound.fields["message_id"])))
        count("s1.captured")
        count(f"s1.captured.{connection.connection_id}")
        log_event("S1", "captured", connector_id=connection.connection_id, event_id=envelope.event_id)
    return taken


def note_events(lane, connection: Connection, taken: int, cursor) -> Connection:
    """Save the cursor and counters only when something changed, so idle polling writes nothing."""
    if not taken and cursor == connection.cursor:
        return connection
    update = {"cursor": cursor, "events": connection.events + taken, "last_error": None}
    if taken:
        now = datetime.now(timezone.utc).isoformat()
        touch(f"s1.last_event.{connection.connection_id}", now)  # the Sensors card reads these, like a webhook capture
        update["last_event_at"] = now
    return save(lane, connection.model_copy(update=update))


# --- Polling

def poll_once(lane, connection: Connection) -> int:
    """Step 1 read from the cursor, step 2 capture, step 3 acknowledge, step 4 keep the new cursor."""
    inbound = connection.manifest.inbound
    page = call(lane, connection, "inbound", query={inbound.cursor_param: connection.cursor or 0})
    taken = take_in(lane, connection, page.get(inbound.items_field) or [])
    if taken and inbound.ack is not None:
        call_ack(lane, connection, taken)
    note_events(lane, connection, len(taken), page.get(inbound.cursor_field, connection.cursor))
    return len(taken)


def call_ack(lane, connection: Connection, ids: list[str]) -> None:
    """Acknowledge is a courtesy: failing it never loses a message, because the cursor already moved on."""
    try:
        call(lane, connection, "ack", {"ids": ids})
    except CallFailed:
        count(f"conn.ack_failed.{connection.connection_id}")


def poll_due(lane) -> None:
    """Poll every live connection whose interval has passed. One failing connection never stops the others."""
    for connection in all_connections(lane):
        if connection.status != "live" or connection.manifest is None or connection.manifest.inbound is None:
            continue
        if time.monotonic() - last_polled.get(connection.connection_id, 0) < connection.manifest.inbound.interval_seconds:
            continue
        last_polled[connection.connection_id] = time.monotonic()
        poll_safely(lane, connection)


def poll_safely(lane, connection: Connection) -> None:
    try:
        poll_once(lane, connection)
    except Exception as error:  # the loop must outlive any one connection; the reason shows on its card
        count(f"conn.poll_failed.{connection.connection_id}")
        detail = error.detail if isinstance(error, CallFailed) else type(error).__name__
        if detail != connection.last_error:
            save(lane, connection.model_copy(update={"last_error": detail}))


def start(lane) -> threading.Thread:
    """The background loop for this lane's connections."""
    def loop() -> None:
        while True:
            poll_due(lane)
            time.sleep(LOOP_SECONDS)
    thread = threading.Thread(target=loop, daemon=True, name="connections")
    thread.start()
    return thread


# --- Push

def accept_push(lane, connection_id: str, body: bytes, signature: str) -> int:
    """A signed push: check the signature with the stored webhook secret, then take the one message in."""
    connection = load(lane, connection_id)
    secret = get_secret(lane, connection_id, "webhook_secret") if connection else None
    if connection is None or connection.status != "live" or not secret or connection.manifest.inbound is None:
        raise PermissionError("not_live")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or "", expected):
        raise PermissionError("signature")
    payload = json.loads(body)
    message = payload.get("message") or payload
    return len(take_in(lane, connection, [message]))
