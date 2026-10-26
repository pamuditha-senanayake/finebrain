# conn_test.py: tests a delivered connection without changing anything on the other side. Reads the feed (if there is
# one) and checks its field names, then calls every read action it can fill. Write actions are listed, never called.
# A database is tested through conn_db.py: sign in, prove the user is read only, read the schema; when the shop gave a
# refund user too, prove it may only add a refund and set an order's status. Nothing is written by the test.
# Used by: api/connect_routes.py. Uses: conn_call.py, conn_db.py, conn_spec.py.
import re

import psycopg

from app.pipeline import conn_db
from app.pipeline.conn_call import CallFailed, Connection, call
from app.pipeline.conn_spec import ENGINES, OrderMap, label, missing_parts, pick

# Config
PLACEHOLDER = re.compile(r"\{(\w+)\}")
FEED = "Feed in"


def result(item: str, ok: bool | None, detail: str) -> dict:
    """One line of the test. ok None means skipped or not called on purpose."""
    return {"item": item, "ok": ok, "detail": detail}


def check_setup(connection: Connection) -> list[dict]:
    """Before any call: settings, everything required, and a key."""
    if connection.manifest is None:
        return [result("Settings", False, "Nothing delivered yet")]
    missing = missing_parts(connection.manifest, connection.needs)
    lines = [result("Settings", not missing, f"Missing: {', '.join(label(m) for m in missing)}" if missing else "Everything required is there")]
    has_key = "api_key" in connection.secrets_set
    return lines + [result("Key", has_key, "Stored encrypted" if has_key else "No key yet")]


def read_feed(lane, connection: Connection) -> tuple[dict, list[dict]]:
    """Step 1: the feed answers with JSON in the declared shape. A refused key shows here first."""
    inbound = connection.manifest.inbound
    try:
        page = call(lane, connection, "inbound", query={inbound.cursor_param: 0})
    except CallFailed as failed:
        return {}, [result(FEED, False, failed.detail if failed.status != 401 else "The key was refused (401)")]
    items = page.get(inbound.items_field)
    if not isinstance(items, list) or inbound.cursor_field not in page:
        return {}, [result(FEED, False, f"Expected '{inbound.items_field}' and '{inbound.cursor_field}' in the answer")]
    sample = next((item for item in reversed(items) if all(pick(item, field) is not None for field in inbound.fields.values())), items[-1] if items else {})
    return sample, [result(FEED, True, f"{len(items)} recent items read")]


def check_fields(connection: Connection, sample: dict) -> list[dict]:
    """Step 2: every mapped field is found in a real item."""
    if not sample:
        return [result("Fields", None, "Nothing in the feed yet; add one and test again")]
    missing = [name for name, field in connection.manifest.inbound.fields.items() if pick(sample, field) is None]
    return [result("Fields", not missing, f"Not found: {', '.join(missing)}" if missing else "Every field found")]


def check_reads(lane, connection: Connection, values: dict) -> list[dict]:
    """Step 3: each read action answers. One that needs an id the test does not have waits for real data."""
    lines = []
    for name, endpoint in connection.manifest.actions.items():
        unfilled = [key for key in PLACEHOLDER.findall(endpoint.path) if values.get(key) is None]
        if endpoint.writes:
            lines.append(result(label(name), None, "Changes data, so not called in a test"))
        elif unfilled:
            lines.append(result(label(name), None, f"Needs a real {unfilled[0]}; checked on first use"))
        else:
            lines.append(try_read(lane, connection, name, values))
    return lines


def try_read(lane, connection: Connection, name: str, values: dict) -> dict:
    try:
        answer = call(lane, connection, name, values)
    except CallFailed as failed:
        return result(label(name), False, "The key was refused (401)" if failed.status == 401 else f"{failed.status or 'No answer'}: {failed.detail[:120]}")
    return result(label(name), True, f"Answered with {', '.join(list(answer)[:4]) or 'an empty object'}")


# --- A database

def database_test(lane, connection: Connection) -> tuple[list[dict], list[dict]]:
    """(lines, readable tables). A user that can change anything fails, however useful it would be."""
    spec = connection.database
    if spec is None or "database_url" not in connection.secrets_set:
        return [result("Settings", spec is not None, "Schemas named" if spec else "Nothing delivered yet"),
                result("Address", "database_url" in connection.secrets_set, "No database address yet")], []
    if spec.engine not in ENGINES:
        return [result("Engine", False, f"The brain reads {', '.join(ENGINES)} directly; connect {spec.engine} through an API instead")], []
    try:
        with conn_db.open_read_only(lane, connection) as db:
            risks, tables = conn_db.write_risks(db, spec.schemas), conn_db.read_schema(db, spec)
    except psycopg.Error as error:
        return [result("Sign in", False, f"Could not sign in: {type(error).__name__}")], []
    return [
        result("Sign in", True, "Signed in"),
        result("Read only", not risks, "This user cannot change anything" if not risks else f"This user {'; '.join(risks)}. Give the brain a read-only user."),
        result("Tables", bool(tables), f"{len(tables)} tables readable" if tables else f"No tables visible in {', '.join(spec.schemas)}"),
        *refund_test(lane, connection),
    ], tables


def refund_test(lane, connection: Connection) -> list[dict]:
    """The refund user, when there is one: it signs in and has exactly the rights a refund needs. It never writes here."""
    if "refund_database_url" not in connection.secrets_set:
        return []
    try:
        with conn_db.open_refunds(lane, connection) as db:
            risks = conn_db.refund_risks(db, connection.database.schemas, connection.orders_map or OrderMap())
            db.rollback()
    except psycopg.Error as error:
        return [result("Refund user", False, f"Could not sign in: {type(error).__name__}")]
    return [result("Refund user", not risks, "May only add a refund and set the order's status" if not risks else f"This user {'; '.join(risks)}. Give only the refund rights.")]


# --- The test

def run_test(lane, connection: Connection) -> tuple[list[dict], dict]:
    """(lines, what to keep on the connection). Stops after the setup when something basic is missing."""
    if connection.kind == "database":
        lines, tables = database_test(lane, connection)
        return lines, {"schema_summary": tables}
    return api_test(lane, connection), {}


def api_test(lane, connection: Connection) -> list[dict]:
    lines = check_setup(connection)
    if any(line["ok"] is False for line in lines):
        return lines
    if connection.manifest.inbound is None:
        return lines + check_reads(lane, connection, {})
    sample, feed = read_feed(lane, connection)
    if feed[0]["ok"] is False:
        return lines + feed
    values = {name: pick(sample, field) for name, field in connection.manifest.inbound.fields.items()}
    return lines + feed + check_fields(connection, sample) + check_reads(lane, connection, values)


def passed(lines: list[dict]) -> bool:
    """Passed when nothing failed and at least one real call answered, so the key is proven."""
    return all(line["ok"] is not False for line in lines) and any(line["ok"] and line["item"] not in ("Settings", "Key") for line in lines)
