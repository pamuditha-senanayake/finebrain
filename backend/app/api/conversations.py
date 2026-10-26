# conversations.py: L3 Conversations, built from the pipeline's own records: each chat's customer messages (masked, as S2
# made them), what the brain's side said (the agent's replies, notices, a person's messages), its runs, and who has it.
# A person can take a chat over (S4 then leaves it to them), reply into the real chat through its connection, hand it
# back, or close it. Used by: routes.py (resources conversations, conversations/:id and the ops). Uses: conversation_log.py,
# stages_orchestrate_chat.py, stages_orchestrate.py, run_steps.py, conn_call.py, tools_chat.py.
import json

from app.pipeline import conversation_log, tools_chat
from app.pipeline import stages_orchestrate_chat as chat
from app.pipeline.conn_call import CallFailed, call, load
from app.pipeline.run_steps import previous_turns
from app.pipeline.stages_orchestrate import signal_of

# Config
OPS = ("takeover", "handback", "sendMessage", "closeConversation")
STATUS_FOR_RUN = {"executed": "executed", "blocked": "blocked", "escalated": "withdrawn"}


class NotPossible(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


# --- Reading one chat

def customer_label(signal) -> str:
    """Never the person's name or email (L3 sees masked data); the token's end tells two visitors apart."""
    return f"Visitor {signal.actor.ref[-4:]}" if signal and signal.actor.ref else "Visitor"


def messages_of(lane, conversation_id: str) -> list[dict]:
    """Customer messages in arrival order, each followed by the replies that answer it (never ordered by clocks)."""
    replies = [{"id": f"{conversation_id}:reply:{n}", "from": r["by"], "author": r["author"], "text": r["text"], "at": r["at"], "citations": [], "after": r.get("after")}
               for n, r in enumerate(lane.records.history(conversation_log.REPLIES_KIND, conversation_id))]
    shown, seen = [], set()
    for version in lane.records.history(chat.MESSAGES_KIND, conversation_id):
        signal = signal_of(lane, version["signal_id"])
        if signal is None or signal.signal_id in seen:  # a redelivered message is shown once
            continue
        seen.add(signal.signal_id)
        shown.append({"id": signal.signal_id, "from": "customer", "author": customer_label(signal), "text": signal.text_masked or "", "at": version.get("at") or lane.now.isoformat(), "citations": []})
        shown += [{k: v for k, v in r.items() if k != "after"} for r in replies if r["after"] == signal.signal_id]
    return shown + [{k: v for k, v in r.items() if k != "after"} for r in replies if r["after"] not in seen]


def actions_of(lane, run_id: str) -> list[dict]:
    """What the agent proposed on each turn of the latest run."""
    record = lane.records.load("run", run_id) or {}
    outcome = record.get("outcome")
    turns = previous_turns(lane, run_id)
    return [{"id": f"{run_id}:{n}", "label": turn["action_type"].replace("_", " "), "tool": turn["action_type"], "criticality": 0,
             "status": "executed" if n < len(turns) - 1 or outcome in ("resolved", "awaiting_customer") else STATUS_FOR_RUN.get(outcome, "proposed"),
             "reason": str((turn.get("arguments") or {}).get("reason") or "")} for n, turn in enumerate(turns)]


def reasoning_of(lane, run_id: str) -> str:
    """The agent's own why, from the trace S10 wrote."""
    record = lane.records.load("run", run_id) or {}
    raw = lane.object_store.get(record.get("trace_object_uri", "")) if record.get("trace_object_uri") else None
    return str(((json.loads(raw) if raw else {}).get("action") or {}).get("rationale_summary") or "")


def view(lane, conversation_id: str) -> dict | None:
    """One chat as the console's Conversation."""
    runs = lane.records.history(chat.RUNS_KIND, conversation_id)
    messages = messages_of(lane, conversation_id)
    if not runs and not messages:
        return None
    latest = runs[-1] if runs else None
    state = lane.records.load(conversation_log.STATE_KIND, conversation_id)
    open_run = latest and not chat.run_closed(lane, latest["run_id"])
    status = state["status"] if state else ("agent" if open_run else "closed")
    first = next((m for m in messages if m["from"] == "customer"), None)
    signal = signal_of(lane, first["id"]) if first else None
    return {"id": conversation_id, "tenantId": lane.seed["tenant_id"], "runId": latest["run_id"] if latest else "", "agentId": latest["task"]["agent_id"] if latest else "",
            "customer": customer_label(signal), "channel": "email" if signal and signal.channel == "email" else "chat", "topic": (first["text"] if first else "")[:80],
            "status": status, "takenOverBy": state["by"] if state and state["status"] == "human" else None,
            "reasoningSummary": reasoning_of(lane, latest["run_id"]) if latest else "", "proposedActions": actions_of(lane, latest["run_id"]) if latest else [],
            "messages": messages, "skillifiedTo": None, "updatedAt": messages[-1]["at"] if messages else lane.now.isoformat()}


def list_view(lane) -> list[dict]:
    """Every chat the pipeline has seen, newest first. A console list, not a run's path."""
    ids = {signal.conversation_id for version in lane.records.list_kind(chat.MESSAGES_KIND) if (signal := signal_of(lane, version["signal_id"])) and signal.conversation_id}
    shown = [v for v in (view(lane, conversation_id) for conversation_id in ids) if v]
    return sorted(shown, key=lambda c: str(c["updatedAt"]), reverse=True)


# --- A person acting on a chat

def where(lane, conversation_id: str):
    """The live connection and its own conversation id, for a chat the brain can write into."""
    connection_id, _, theirs = conversation_id.partition(":")
    connection = load(lane, connection_id)
    if connection is None or connection.status != "live" or connection.manifest is None:
        raise NotPossible(409, "This chat cannot be answered from here")
    return connection, theirs


def send(lane, conversation_id: str, persona: str, text: str) -> dict:
    """A person's reply into the real chat, under its own key, then kept with the chat."""
    if not text.strip():
        raise NotPossible(422, "Write a message first")
    if not conversation_log.taken_over(lane, conversation_id):
        raise NotPossible(409, "Take the conversation over first, so the agent stays out")
    connection, theirs = where(lane, conversation_id)
    sent = len(lane.records.history(conversation_log.REPLIES_KIND, conversation_id))
    answer = tools_chat.send(lane, connection, theirs, {"message_plain": text.strip()}, f"{lane.seed['tenant_id']}:human:{conversation_id}:{sent}")
    if answer["status"] != "succeeded":
        raise NotPossible(502, "The chat did not take the message. Try again.")
    last = lane.records.load(chat.MESSAGES_KIND, conversation_id)
    conversation_log.remember_reply(lane, conversation_id, text.strip(), "human", lane.seed["people"][persona].get("name", persona), after=last["signal_id"] if last else None)
    return view(lane, conversation_id)


def run_op(lane, op: str, body: dict, persona: str) -> dict:
    """Take over, hand back, send, or close one chat."""
    conversation_id = str(body.get("conversationId") or "")
    if view(lane, conversation_id) is None:
        raise NotPossible(404, "not_found")
    if op == "sendMessage":
        return send(lane, conversation_id, persona, str(body.get("text") or ""))
    if op == "closeConversation":
        close_on_their_side(lane, conversation_id)
    status = {"takeover": "human", "handback": "agent", "closeConversation": "closed"}[op]
    conversation_log.set_state(lane, conversation_id, status, persona, str(body.get("note") or ""))
    return view(lane, conversation_id)


def close_on_their_side(lane, conversation_id: str) -> None:
    """Best effort: a site that can close a chat is told; the brain's record closes either way."""
    try:
        connection, theirs = where(lane, conversation_id)
        if "close" in connection.manifest.actions:
            call(lane, connection, "close", {"conversation_id": theirs})
    except (NotPossible, CallFailed):
        pass
