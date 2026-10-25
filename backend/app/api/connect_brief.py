# connect_brief.py: the brief for the other side's coding agent, written from what this connection is for, and reading
# their agent's answer back. The answer is read by plain parsing, so no model ever sees the keys in it.
# Used by: connect_routes.py, connect_guide.py. Uses: connect_brief_db.py, conn_call.py, conn_spec.py.
import json
import re

from app.api import connect_brief_db
from app.pipeline.conn_call import Connection
from app.pipeline.conn_spec import DatabaseSpec, Manifest

# Config
ANSWER_FENCE = re.compile(r"```brain-connection\s*(\{.*?\})\s*```", re.DOTALL)
ANY_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
KEY_LINE = re.compile(r"(api[_ ]?key|webhook[_ ]?secret|push[_ ]?secret|database[_ ]?url)\s*[:=]\s*[\"'`]?([^\s\"'`]+)", re.IGNORECASE)
SECRET_FOR = {"api": "api_key", "webhook": "webhook_secret", "push": "webhook_secret", "database": "database_url"}
FEED_SHAPE = {"poll": {"method": "GET", "path": "/path/of/the/feed"}, "cursor_param": "since", "cursor_field": "nextSince", "items_field": "items",
              "fields": {"message_id": "id", "conversation_id": "thread_id", "sender": "from", "text": "body", "customer_id": "customer_id"},
              "only_sender": "customer", "interval_seconds": 2}


# --- The brief

def needs_lines(connection: Connection) -> str:
    lines = [f"- `{need.name}` ({'required' if need.required else 'optional'}{', changes data' if need.writes else ''}): {need.text}" for need in connection.needs]
    return "\n".join(lines) or "- (none drafted yet)"


def answer_example(connection: Connection) -> dict:
    """The shape their agent answers in, with one entry per need, so it is easy to fill."""
    actions = {need.name: {"method": "POST" if need.writes else "GET", "path": f"/path/for/{need.name}", **({"writes": True} if need.writes else {})}
               for need in connection.needs if need.name != "inbound"}
    manifest = {"name": connection.system or connection.name, "purpose": connection.purpose, "base_url": "https://...", "auth": "bearer",
                "actions": actions} | ({"inbound": FEED_SHAPE} if any(need.name == "inbound" for need in connection.needs) else {})
    return {"manifest": manifest, "api_key": "<a new key made only for the brain>", "webhook_secret": "<only if you push, else leave out>"}


def brief(connection: Connection, company: str) -> str:
    """The request their coding agent can follow as is. Written from the needs, so it fits whatever is being connected."""
    if connection.kind == "database":
        return connect_brief_db.brief(connection, company)
    feed = any(need.name == "inbound" for need in connection.needs)
    feed_rules = ("\n- The feed is read with a cursor: return the items and the next cursor; the brain sends it back next time. Never resend old items."
                  "\n- Each item says who sent it and which thread it belongs to." if feed else "")
    return f"""# Request from {company}: connect {connection.system or connection.name}

{company} runs a company brain, an AI system that works with its tools under rules and approvals.
Goal: {connection.goal or "(not described yet)"}

Please make the endpoints below available to the brain, then answer in the exact format at the end.

## What the brain needs
{needs_lines(connection)}

Endpoints that already exist are fine; only describe them. Paths may contain placeholders such as `{{order_id}}`; the brain fills them.

## Rules
- HTTPS only. Every call from the brain sends `Authorization: Bearer <API key>`. Make a new key for the brain, allowed only these endpoints.
- Answer JSON. Errors as `{{"error": "..."}}` with real status codes (401 bad key, 404 not found, 409 already done, 422 rule broken).
- No login wall in front of these paths (for example Vercel Deployment Protection).
- Anything that changes data must be safe to repeat: the same call sent twice must not act twice.{feed_rules}

## Answer in exactly this format
Reply with one block like this (fill in real paths, field names and keys), and nothing secret anywhere else:

```brain-connection
{json.dumps(answer_example(connection), indent=2)}
```

The person who asked will paste your whole answer into the brain. The brain reads the block, stores the key encrypted, and tests every read. It never calls anything that changes data in a test."""


# --- Reading their answer

def find_block(text: str) -> dict | None:
    """The brain-connection block, else any JSON block or the whole text as JSON."""
    for pattern in (ANSWER_FENCE, ANY_FENCE):
        for match in pattern.finditer(text):
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    try:
        found = json.loads(text)
        return found if isinstance(found, dict) else None
    except json.JSONDecodeError:
        return None


def keys_in_lines(text: str) -> dict:
    """Keys written as lines (API_KEY=...), for answers that keep them out of the JSON."""
    keys = {}
    for name, value in KEY_LINE.findall(text):
        keys[SECRET_FOR[re.split(r"[_ ]", name.lower())[0]]] = value
    return keys


def read_answer(text: str) -> tuple[Manifest | DatabaseSpec | None, dict, list[str]]:
    """(settings, secrets, problems) from their agent's whole answer. Placeholder keys like <...> are ignored."""
    block = find_block(text)
    secrets = keys_in_lines(text) | {name: str((block or {})[name]) for name in SECRET_FOR.values() if (block or {}).get(name)}
    secrets = {name: value for name, value in secrets.items() if "<" not in value}
    if block is None:
        return None, secrets, ["No settings block found. Paste the whole answer, including the ```brain-connection block."]
    try:
        if "database" in block:
            return DatabaseSpec.model_validate(block["database"]), secrets, []
        return Manifest.model_validate(block.get("manifest", block)), secrets, []
    except ValueError as error:
        problems = [f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in getattr(error, "errors", lambda: [])()]
        return None, secrets, problems or [str(error)]
