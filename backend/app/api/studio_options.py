# studio_options.py: the real choices behind Workflow Studio's pick lists, taken from what the pipeline reads: the endpoints
# S9 serves, the capabilities S5 and S7 check (plus any an agent in the graph already holds), the models, the currencies a
# limit may use, and the events each message source sends. A pick list built from these can only offer what exists.
# Used by: studio_routes.py (GET studio/options), studio_findings.py. Uses: tool_runners.py, stages_govern.py, stages_retrieve.py, llm.py, studio_activity.py.
from app.api.studio_activity import message_sources
from app.pipeline import llm
from app.pipeline.stages_govern import CAPABILITY_FOR_ACTION
from app.pipeline.stages_retrieve import READ_CAPABILITY
from app.pipeline.tool_runners import RUNNERS

# Config
CAPABILITY_LABELS = {READ_CAPABILITY: "Read knowledge", "reply.draft": "Reply to customers", "refund.propose": "Propose refunds", "escalate": "Hand to a person"}
CHECKED_CAPABILITIES = {READ_CAPABILITY, *CAPABILITY_FOR_ACTION.values()}  # what S5 and S7 actually check
MODELS = {llm.REASON_MODEL: "Sonnet: reasons and drafts", llm.FAST_MODEL: "Haiku: fast checks", llm.CAREFUL_MODEL: "Opus: rare, careful calls"}
CURRENCIES = ["LKR", "USD", "EUR", "GBP", "INR", "AUD", "SGD", "AED"]
FEED_EVENTS = ["message.created"]  # what a connection's message feed sends (conn_inbound.py)
CHANNEL_EVENTS = {"email": ["email.received"], "chat": ["chat.message"], "upload": ["document.uploaded"], "webhook": ["webhook.received"]}


def labelled(values: dict[str, str]) -> list[dict]:
    return [{"id": key, "label": label} for key, label in values.items()]


def capabilities(lane) -> list[dict]:
    """The checked capabilities first, then any other one an agent already holds, so nothing in use disappears."""
    held = sorted({c for agent in lane.graph.latest("agent") for c in agent.get("capabilities", [])} - CHECKED_CAPABILITIES)
    return labelled({c: CAPABILITY_LABELS.get(c, c) for c in sorted(CHECKED_CAPABILITIES)} | {c: f"{c} (no check uses it)" for c in held})


def options(lane) -> dict:
    """Everything Studio's forms may offer, in one read."""
    sources = message_sources(lane)
    return {
        "endpoints": labelled(RUNNERS), "capabilities": capabilities(lane), "models": labelled(MODELS), "currencies": CURRENCIES,
        "events": {**CHANNEL_EVENTS, **{source_id: FEED_EVENTS for source_id in sources}},
    }
