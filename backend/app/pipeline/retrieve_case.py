# retrieve_case.py: S5 for one run. Knowledge comes from stages_retrieve.py; this adds what is true about this case only:
# the customer's latest orders from the shop's database (read only, as of the asked time) and the chat so far. Both obey
# the same access rules as knowledge, and both are left out, never guessed, when they cannot be read.
# Used by: run_steps.py (S4's run asks S5 here). Uses: stages_retrieve.py, tools_read.py, stages_orchestrate_chat.py, observe.py.
from datetime import datetime

from app.pipeline import stages_orchestrate_chat as chat
from app.pipeline import conn_db, stages_retrieve, tools_read
from app.pipeline.contracts_reason import ContextBundle, ContextItem, ContextQuery, DeniedReason
from app.pipeline.observe import count, log_event, log_seam

# Config
ORDER_SENSITIVITY = "confidential"  # a customer's orders and payments
CHAT_SENSITIVITY = "internal"  # masked chat text
CHAT_MESSAGES_SHOWN = 20  # the latest messages; a long chat keeps its end, where the case is


# --- Orders from the shop

def money(amount_minor: int, currency: str) -> str:
    return f"{currency} {amount_minor / 100:,.2f}"


def order_text(order: dict, as_of: datetime | None, zone) -> str:
    """One order in plain words, with the money already returned on it. No name or email: those stay in the shop."""
    paid = order["paid_at"].astimezone(zone)
    returned = tools_read.refunded_minor(order, as_of)
    refunds = f"refunded {money(returned, order['currency'])} so far" if returned else "no refund yet"
    return (f"Order {order['order_id']}: {order['product']}, {money(order['total_minor'], order['currency'])}, paid {paid.day} {paid:%B %Y} "
            f"with payment {order['payment_ref']}; status {order['status']}; {refunds}.")


def order_item(order: dict, connection_id: str, as_of: datetime | None, zone, now: datetime) -> dict:
    return {"item_id": f"order:{order['order_id']}", "kind": "fact", "text": order_text(order, as_of, zone),
            "source": {"document_id": f"{connection_id}:orders", "uri": f"db://{connection_id}/orders/{order['order_id']}"},
            "valid_from": order["paid_at"], "valid_to": None, "recorded_at": now, "verified_by": None, "version_ref": None,
            "score": 1.0, "sensitivity": ORDER_SENSITIVITY}


def customer_key(lane, customer_ref: str | None) -> str | None:
    """How the shop knows the customer: the email behind S2's token (from the vault), or the shop's own customer id when
    the chat gave one. An anonymous visitor's token has nothing behind it, so they have no orders to show."""
    if not customer_ref:
        return None
    if customer_ref.startswith("pii_tok_"):
        return lane.vault.get(customer_ref)
    return customer_ref


def orders_for(lane, query: ContextQuery, now: datetime) -> tuple[list[dict], str]:
    """The case customer's orders as items, and a note on how the read went."""
    connection = tools_read.orders_connection(lane)
    customer = customer_key(lane, query.customer_ref)
    if connection is None or not customer:
        return [], "no shop or no customer"
    try:
        orders = tools_read.find_customer_orders(lane, connection, customer)
    except (tools_read.ReadUnavailable, conn_db.NotAllowed) as error:  # down, or a map that is not plain names: no orders, never a crash
        count("s5.orders_unavailable")
        log_event("S5", "orders_unavailable", run_id=query.run_id, error=str(error))
        return [], "orders unavailable"
    as_of = query.as_of_valid
    known = [o for o in orders if as_of is None or o["paid_at"] <= as_of]  # an order paid after the asked time did not exist yet
    return [order_item(o, connection.connection_id, as_of, now.tzinfo, now) for o in known], f"{len(known)} orders"


# --- The chat so far

def chat_items(lane, query: ContextQuery, now: datetime) -> list[dict]:
    """The case's chat, oldest first, masked as S2 stored it."""
    if not query.conversation_id:
        return []
    ids = [v["signal_id"] for v in lane.records.history(chat.MESSAGES_KIND, query.conversation_id)][-CHAT_MESSAGES_SHOWN:]
    stored = [lane.records.load("signal", signal_id) for signal_id in dict.fromkeys(ids)]
    return [{"item_id": f"msg:{s['signal_id']}", "kind": "chunk", "text": f"Customer wrote: {s.get('text_masked') or ''}",
             "source": {"document_id": f"conversation:{query.conversation_id}", "uri": f"chat://{query.conversation_id}/{s['signal_id']}"},
             "valid_from": None, "valid_to": None, "recorded_at": now, "verified_by": None, "version_ref": None,
             "score": 1.0, "sensitivity": CHAT_SENSITIVITY} for s in stored if s]


# --- S5 for a run

def retrieve_for_run(lane, query: ContextQuery) -> tuple[ContextBundle, object]:
    """Knowledge, then this case's orders and chat, all through one access check. One bundle and one access decision."""
    # Step 1: knowledge, with its own access decision (a principal without kb.read gets nothing at all)
    bundle, decision = stages_retrieve.retrieve(query, lane.chunks, lane.embed, lane.rerank, lane.seed["people"], lane.new_id, lane.now, lane.commons)
    if decision.decision != "allow":
        return bundle, decision

    # Step 2: the case's orders and chat, kept only when the principal (and the person it acts for) may read them
    orders, note = orders_for(lane, query, lane.now)
    case = orders + chat_items(lane, query, lane.now)
    readable = stages_retrieve.readable_for(query, lane.seed["people"])
    shown = [ContextItem.model_validate(item) for item in case if item["sensitivity"] in readable]
    withheld = len(case) - len(shown)

    # Step 3: one bundle and one decision; log the seam with ids only (the texts can hold personal data)
    denied = bundle.denied_count + withheld
    merged = bundle.model_copy(update={"items": [*bundle.items, *shown], "denied_count": denied,
                                       "denied_reasons": [DeniedReason(rule_id=stages_retrieve.SENSITIVITY_RULE_ID, count=denied)] if denied else []})
    decision = decision.model_copy(update={"reason": f"{decision.reason}; case: {note}, {len(shown)} shown, {withheld} withheld"})
    log_seam("S5", {"run_id": query.run_id, "principal": query.principal.id, "customer": bool(query.customer_ref), "conversation": query.conversation_id},
             {"items": [item.item_id for item in merged.items], "denied_count": denied, "scope": merged.scope.model_dump() if merged.scope else None})
    return merged, decision
