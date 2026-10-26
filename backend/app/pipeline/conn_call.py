# conn_call.py: keeps connections and calls their actions. The manifest and status live in records (kind "connection");
# secrets live in the encrypted vault under "secret:<connection>:<name>", so a record, a log or the console never holds one.
# The live shop database is also named in a role record ("connection_role", "orders"), so a run finds it by key.
# Used by: conn_test.py, conn_inbound.py, api/connect_routes.py, chat tools. Uses: conn_spec.py, observe.py.
import os

import httpx
from pydantic import BaseModel

from app.pipeline.conn_spec import SECRET_NAMES, DatabaseSpec, Manifest, Need, OrderMap, fill
from app.pipeline.observe import count, log_event

# Config
CALL_TIMEOUT_SECONDS = float(os.environ.get("CONNECTION_TIMEOUT_SECONDS", "10"))
ROLE_KIND, ORDERS = "connection_role", "orders"
http = httpx.Client(follow_redirects=False)  # one pool for every connection; tests swap it for a fake transport


class Connection(BaseModel):
    """One connection's state, without secrets."""
    connection_id: str
    purpose: str = "general"
    name: str
    system: str = ""  # what is being connected, in the person's words
    goal: str = ""  # what the brain should do with it
    needs: list[Need] = []
    platform: str = ""  # the system it belongs to, e.g. "Finebase Labs portal"; connections are grouped by it
    kind: str = "api"  # api, database or other (conn_spec.KINDS)
    later: list[str] = []  # other connections the person mentioned, to start once this one is done
    database: DatabaseSpec | None = None
    orders_map: OrderMap | None = None  # set on a shop database whose orders S5 may look up
    schema_summary: list[dict] = []  # tables the brain can read, with their columns, from the last database test
    status: str = "waiting"  # waiting for the other party, delivered, tested, live, paused
    manifest: Manifest | None = None
    secrets_set: list[str] = []
    tests: list[dict] = []
    tested_at: str | None = None
    cursor: int | str | None = None
    created_by: str
    events: int = 0
    last_event_at: str | None = None
    last_error: str | None = None


class Role(BaseModel):
    """Which connection plays a role for the tenant; None when none does."""
    connection_id: str | None


class CallFailed(Exception):
    """The other side answered with an error or did not answer."""
    def __init__(self, action: str, status: int | None, detail: str):
        super().__init__(f"{action}: {status or 'no answer'} {detail}")
        self.action, self.status, self.detail = action, status, detail


# --- Keeping connections

def load(lane, connection_id: str) -> Connection | None:
    stored = lane.records.load("connection", connection_id)
    return Connection.model_validate(stored) if stored else None


def save(lane, connection: Connection) -> Connection:
    lane.records.save("connection", connection.connection_id, connection)
    if connection.kind == "database":
        note_role(lane, connection)
    return connection


def plays_orders(connection: Connection) -> bool:
    return connection.kind == "database" and connection.status == "live" and connection.orders_map is not None


def note_role(lane, connection: Connection) -> None:
    """Point the orders role at a live shop database, or clear it when the one it named stops being one."""
    current = (lane.records.load(ROLE_KIND, ORDERS) or {}).get("connection_id")
    if plays_orders(connection) and current != connection.connection_id:
        lane.records.save(ROLE_KIND, ORDERS, Role(connection_id=connection.connection_id))
    elif not plays_orders(connection) and current == connection.connection_id:
        lane.records.save(ROLE_KIND, ORDERS, Role(connection_id=None))


def orders_database(lane) -> Connection | None:
    """The live shop database, read by key through its role. None when the tenant has none."""
    role = lane.records.load(ROLE_KIND, ORDERS)
    connection = load(lane, role["connection_id"]) if role and role["connection_id"] else None
    return connection if connection and plays_orders(connection) else None


def note_roles(lane) -> None:
    """Once at start: name the roles of connections saved before roles existed. Not on any run's path."""
    for connection in all_connections(lane):
        if connection.kind == "database":
            note_role(lane, connection)


def all_connections(lane) -> list[Connection]:
    return [Connection.model_validate(stored) for stored in lane.records.list_kind("connection")]


def remove(lane, connection: Connection) -> None:
    """Erase the connection and every secret it kept, and any role it played."""
    note_role(lane, connection.model_copy(update={"status": "removed"}))
    for name in connection.secrets_set:
        lane.vault.pop(secret_key(connection.connection_id, name), None)
    lane.records.purge("connection", connection.connection_id)


def secret_key(connection_id: str, name: str) -> str:
    return f"secret:{connection_id}:{name}"


def set_secret(lane, connection: Connection, name: str, value: str) -> Connection:
    """Store one secret encrypted and note only that it is set. A new value replaces the old one."""
    if name not in SECRET_NAMES:
        raise ValueError(f"unknown secret {name}")
    key = secret_key(connection.connection_id, name)
    if key in lane.vault:
        del lane.vault[key]  # the vault keeps the first value it is given
    lane.vault[key] = value
    return connection.model_copy(update={"secrets_set": sorted(set(connection.secrets_set) | {name})})


def get_secret(lane, connection_id: str, name: str) -> str | None:
    try:
        return lane.vault[secret_key(connection_id, name)]
    except KeyError:
        return None


# --- Calling the other side

def headers_for(lane, connection: Connection) -> dict:
    """Auth header from the stored key. Bearer adds the word; header sends the key as is."""
    key = get_secret(lane, connection.connection_id, "api_key") or ""
    manifest = connection.manifest
    value = f"Bearer {key}" if manifest.auth == "bearer" else key
    return {manifest.auth_header: value, "Content-Type": "application/json", "Accept": "application/json"}


def call(lane, connection: Connection, action: str, values: dict | None = None, query: dict | None = None) -> dict:
    """Call one named action (or "inbound" for the poll) and return its JSON. Errors raise CallFailed, never a raw exception."""
    manifest = connection.manifest
    feed = manifest.inbound
    endpoint = {"inbound": feed.poll if feed else None, "ack": feed.ack if feed else None}.get(action) or manifest.actions.get(action)
    if endpoint is None:
        raise CallFailed(action, None, "not declared in the manifest")
    values = values or {}
    url = manifest.base_url.rstrip("/") + fill(endpoint.path, values)
    body = fill(endpoint.body, values) if endpoint.body is not None else None
    try:
        answer = http.request(endpoint.method, url, headers=headers_for(lane, connection), json=body, params=query, timeout=CALL_TIMEOUT_SECONDS)
    except httpx.HTTPError as error:
        count(f"conn.unreachable.{connection.connection_id}")
        raise CallFailed(action, None, type(error).__name__) from None
    if answer.status_code >= 400:
        count(f"conn.error.{connection.connection_id}")
        log_event("CONN", "call_failed", connection_id=connection.connection_id, action=action, status=answer.status_code)
        raise CallFailed(action, answer.status_code, answer.text[:200])
    if not answer.content:
        return {}
    if "json" not in answer.headers.get("content-type", ""):
        raise CallFailed(action, answer.status_code, "answered with a page, not JSON (a login wall or a wrong path)")
    return answer.json()
