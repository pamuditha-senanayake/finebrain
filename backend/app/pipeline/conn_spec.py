# conn_spec.py: what a connection is. Needs say what the brain wants from a system (drafted with the guide). A manifest
# (no secrets) says where the system lives, how the brain signs in, an optional feed into the brain, and the named actions.
# Used by: conn_call.py, conn_test.py, conn_inbound.py, api/connect_routes.py, api/connect_guide.py. Uses: nothing local.
from typing import Literal

from pydantic import BaseModel, Field

# Config
SECRET_NAMES = ("api_key", "webhook_secret", "database_url")  # kept in the encrypted vault, never in the manifest
KINDS = ("api", "database", "other")  # a website or app with an API, a database, or not decided yet
ENGINES = ("postgres",)  # databases the brain reads directly today; others connect through an API


class Endpoint(BaseModel):
    """One call the brain can make. Placeholders like {conversation_id} are filled at call time."""
    method: Literal["GET", "POST", "PATCH", "PUT", "DELETE"]
    path: str = Field(description="Path after base_url, e.g. /api/hub/messages")
    body: dict | None = Field(default=None, description="JSON body; a whole-value placeholder like \"{text}\" keeps the value's type")
    writes: bool = Field(default=False, description="True when the call changes something on the other side; tests never call it")


class Inbound(BaseModel):
    """How customer messages reach the brain: polled with a cursor, and optionally pushed with a signature."""
    poll: Endpoint
    cursor_param: str = "since"
    cursor_field: str = "nextSince"
    items_field: str = "messages"
    fields: dict[str, str] = Field(description="Brain name to their field, dotted for nested: conversation_id, message_id, sender, text, customer_id, created_at")
    only_sender: str | None = Field(default="customer", description="Keep only messages from this sender value")
    ack: Endpoint | None = None
    interval_seconds: float = 2.0
    push_signature_header: str | None = None


class Need(BaseModel):
    """One thing the brain wants from the system. "inbound" is a feed into the brain; every other name is an action."""
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    text: str = Field(max_length=300)
    writes: bool = False
    required: bool = True


class Manifest(BaseModel):
    """What the other party hands back. The brain stores it as is, and the secrets apart."""
    name: str
    purpose: str = "general"
    base_url: str
    auth: Literal["bearer", "header"] = "bearer"
    auth_header: str = "Authorization"
    inbound: Inbound | None = None
    actions: dict[str, Endpoint]
    docs_url: str | None = None


class DatabaseSpec(BaseModel):
    """What the other side hands back for a database. The address and password live in the secret database_url."""
    engine: str = Field(description="postgres today; others connect through an API")
    schemas: list[str] = Field(min_length=1, description="The only schemas the brain may read")
    tables: list[str] = Field(default=[], description="Optional: only these tables, as schema.table")
    notes: str = Field(default="", max_length=1000, description="What the main tables mean, in plain words")


# --- Starting needs, for when no guide drafted them

TEMPLATES = {
    "website_chat": [
        Need(name="inbound", text="New customer messages, oldest first, with a cursor so none is read twice"),
        Need(name="reply", text="Send a reply into the customer's chat (body, optional quick-reply buttons)", writes=True),
        Need(name="conversation", text="Read one conversation: its customer, their orders and earlier messages"),
        Need(name="close", text="Mark a conversation resolved", writes=True, required=False),
        Need(name="refund_file", text="File a refund on an order", writes=True, required=False),
        Need(name="refund_decide", text="Approve or deny a filed refund; approving sets the order to refunded", writes=True, required=False),
    ],
}
LABELS = {"inbound": "Feed in", "reply": "Reply", "conversation": "Conversation", "typing": "Typing", "close": "Close chat",
          "customer": "Customer", "orders": "Orders", "refund_file": "File refund", "refund_decide": "Decide refund"}


def label(name: str) -> str:
    """Short name for a need or action: known ones by table, others from their name."""
    return LABELS.get(name) or name.replace("_", " ").capitalize()


def missing_parts(manifest: Manifest, needs: list[Need]) -> list[str]:
    """Required needs the manifest does not cover yet."""
    covered = set(manifest.actions) | ({"inbound"} if manifest.inbound else set())
    return [need.name for need in needs if need.required and need.name not in covered]


# --- Filling placeholders

def fill(template, values: dict):
    """Replace {name} placeholders. A string that is only a placeholder takes the value itself, so lists stay lists."""
    if isinstance(template, dict):
        return {key: fill(value, values) for key, value in template.items()}
    if isinstance(template, list):
        return [fill(value, values) for value in template]
    if not isinstance(template, str):
        return template
    if template.startswith("{") and template.endswith("}") and template[1:-1] in values:
        return values[template[1:-1]]
    return template.format_map(SafeValues(values))


class SafeValues(dict):
    """Leaves unknown placeholders as they are, so a path with no value fails loudly at the other side, not here."""
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def pick(item: dict, dotted: str):
    """A nested field by its dotted name, e.g. conversations.customer_id; None when any part is missing."""
    value = item
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value
