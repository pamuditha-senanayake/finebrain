# connect_guide.py: the connection guide. Claude asks what is being connected and what the brain should do with it,
# then drafts the connection's needs with a tool; the brief is written from them. Later it answers questions, knowing
# the connection's state and last test. It never sees a key.
# Used by: connect_routes.py. Uses: connect_guide_prompt.py, conn_call.py, conn_spec.py, observe.py.
import re

from pydantic import ValidationError

from app.api.connect_guide_prompt import DRAFT_TOOL, GUIDE_SYSTEM
from app.pipeline.conn_call import Connection, load, save
from app.pipeline.conn_spec import KINDS, Need
from app.pipeline.observe import log_event

# Config
HISTORY_TURNS = 16
NO_MODEL = "I can't think right now (no model key). Please try again later."


def state_of(connection: Connection | None) -> str:
    """What the guide may know: the draft, the status, the last test. Never a secret, only which ones are set."""
    if connection is None:
        return "No connection yet. Start by asking what they want to connect."
    if not connection.connection_id:
        chosen = {"api": "a website or app (api)", "database": "a database"}.get(connection.kind, "not chosen yet")
        return f"New connection, nothing drafted yet. Platform: {connection.platform or 'not named yet'}. Type: {chosen}."
    needs = "\n".join(f"- {n.name}: {n.text}{' (changes data)' if n.writes else ''}" for n in connection.needs) or "- none"
    tests = "\n".join(f"- {line['item']}: {'pass' if line['ok'] else 'not called' if line['ok'] is None else 'FAIL'} ({line['detail']})" for line in connection.tests)
    return (f"name: {connection.name}\nplatform: {connection.platform}\ntype: {connection.kind}\nsystem: {connection.system}\ngoal: {connection.goal}\n"
            f"status: {connection.status}\nneeds:\n{needs}\nto do after this one: {'; '.join(connection.later) or 'nothing'}\n"
            f"secrets set: {', '.join(connection.secrets_set) or 'none'}\nlast error: {connection.last_error or 'none'}\nlast test:\n{tests or '- not tested yet'}")


def slug(name: str) -> str:
    return "conn_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "new")


def free_id(lane, name: str) -> str:
    """A new id from the name, with a number when the name is taken."""
    base, number = slug(name), 2
    connection_id = base
    while load(lane, connection_id) is not None:
        connection_id, number = f"{base}_{number}", number + 1
    return connection_id


def apply_draft(lane, connection: Connection | None, draft: dict, person: str) -> Connection:
    """Create the connection, or update its description and needs. Bad needs are dropped, not guessed."""
    database = draft.get("kind") == "database"
    needs = [Need(name="inbound", text=str(draft["feed"])[:300])] if draft.get("feed") and not database else []
    for raw in draft.get("needs") or []:
        if "inbound" in str(raw.get("name")) and needs:
            continue  # the feed is already there; a need named like it would only duplicate it
        try:
            needs.append(Need.model_validate(raw | ({"writes": False} if database else {})))  # a database is only ever read
        except ValidationError:
            log_event("CONN", "need_dropped", name=str(raw.get("name"))[:40])
    fields = {"name": str(draft["name"])[:80], "system": str(draft["system"])[:200], "goal": str(draft["goal"])[:300],
              "purpose": str(draft.get("purpose") or "general")[:40], "needs": needs, "kind": draft.get("kind") if draft.get("kind") in KINDS else "api",
              "platform": str(draft.get("platform") or draft["system"])[:80], "later": [str(item)[:200] for item in draft.get("later") or []][:5]}
    if connection is None or not connection.connection_id:
        return save(lane, Connection(connection_id=free_id(lane, fields["name"]), created_by=person, **fields))
    retest = {"tests": [], "status": "delivered"} if connection.status == "tested" else {"tests": []}  # new needs, so the last test no longer holds
    return save(lane, connection.model_copy(update=fields | (retest if connection.status != "live" else {})))


def guide(chatter, lane, connection: Connection | None, company: str, turns: list[dict], person: str, start: dict | None = None) -> tuple[str, Connection | None]:
    """One answer from Claude, and the connection as it stands after any draft. start carries the chosen type and platform
    of a new connection, so the guide begins on the right path."""
    if chatter is None:
        return NO_MODEL, connection
    if connection is None and start:
        connection = Connection(connection_id="", name="", created_by=person, **start)  # shown to the guide only; saved when drafted
    messages = [{"role": t["role"], "content": str(t["text"])[:4000]} for t in turns[-HISTORY_TURNS:] if t.get("role") in ("user", "assistant") and t.get("text")]
    try:
        reply = chatter(GUIDE_SYSTEM.format(company=company, state=state_of(connection)), messages, [DRAFT_TOOL])
    except Exception as error:  # an outage answers plainly; the person can try again
        log_event("CONN", "guide_unavailable", error=type(error).__name__)
        return "I can't answer right now. Please try again in a moment.", connection
    text = "".join(getattr(block, "text", "") for block in reply.content if block.type == "text").strip()
    draft = next((block.input for block in reply.content if block.type == "tool_use" and block.name == "draft_connection"), None)
    fallback = "Updated. Run the test again to check." if connection and (connection.manifest or connection.database) else "The request is ready to copy."
    database_fallback = "The request is ready. It asks them for a separate user that can only read, made just for the brain."
    if draft is not None:
        connection = apply_draft(lane, connection, draft, person)
    if not text and connection is not None and connection.kind == "database" and not connection.database:
        fallback = database_fallback
    return text or fallback, connection if connection is None or connection.connection_id else None
