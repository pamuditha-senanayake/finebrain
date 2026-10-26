# govern_payments.py: the payment S7 checks a refund against, read at decision time from the source of truth. With a live
# shop database: the order behind the payment ref, only if it is the case customer's, with the refunds the shop and the
# brain already made. Without one: the payments the golden samples carry. A read that fails gives no payment, so the
# refund escalates. Used by: run_steps.py (govern_once, act_and_finish). Uses: tools_read.py, retrieve_case.py, conn_db.py, observe.py.
from pydantic import BaseModel

from app.pipeline import conn_db, retrieve_case, tools_read
from app.pipeline.observe import count, log_event

# Config
REFUNDED_KIND = "payment_refunded"  # records kind keyed by payment ref: what the brain already returned on it


class Refunded(BaseModel):
    payment_ref: str
    amount_minor: int
    run_id: str


def payments_for(lane, signal, payment_ref: str | None) -> dict:
    """payment ref to payment, for S7. Only the payment this action names, and only when the case customer owns it."""
    connection = tools_read.orders_connection(lane)
    if not payment_ref or connection is None:
        return lane.seed["payments"]
    customer = retrieve_case.customer_key(lane, signal.actor.ref if signal and signal.actor.type == "customer" else None)
    if not customer:
        return {}
    try:
        payment = tools_read.find_payment(lane, connection, payment_ref, customer)
    except (tools_read.ReadUnavailable, conn_db.NotAllowed) as error:
        count("s7.payment_unavailable")
        log_event("S7", "payment_unavailable", error=str(error))
        return {}
    if payment is None:
        return {}
    returned = lane.records.load(REFUNDED_KIND, payment_ref)
    brain_refunded = sum(version["amount_minor"] for version in lane.records.history(REFUNDED_KIND, payment_ref)) if returned else 0
    return {payment_ref: {**payment, "refunded_minor": max(payment["refunded_minor"], brain_refunded)}}  # the larger: the shop may not know yet


def note_refund(lane, payment_ref: str, amount_minor: int, run_id: str) -> None:
    """After S9 refunded: remember it, so no later run can refund the same payment again before the shop records it.
    Best effort: the money already moved, so a records outage must not stop S10 from recording the run; it is counted and logged."""
    try:
        lane.records.save(REFUNDED_KIND, payment_ref, Refunded(payment_ref=payment_ref, amount_minor=amount_minor, run_id=run_id))
    except Exception as error:
        count("s9.refund_not_noted")
        log_event("S9", "refund_not_noted", payment_ref=payment_ref, run_id=run_id, error=type(error).__name__)
