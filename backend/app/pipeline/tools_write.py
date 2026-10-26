# tools_write.py: write tools, the brain's way to change a connected system. Today one: a refund in the shop's own database,
# signed in as the refund user the shop gave (it may only add a refund and set an order's status). One transaction locks
# the run customer's own order, checks the refund against it, adds the refund under an id made from S9's idempotency key,
# and sets the order's status. So a retry, a crash or two workers never refund twice, two runs never return more than was
# paid, and no run refunds another customer's order, whatever S7 saw earlier.
# Used by: run_finish.py (S9's runner for issue_refund). Uses: conn_db.py, conn_call.py, tools_read.py, retrieve_case.py, stages_orchestrate.py, observe.py.
import hashlib

import psycopg

from app.pipeline import conn_db, retrieve_case
from app.pipeline.conn_call import Connection, orders_database
from app.pipeline.observe import count, log_event
from app.pipeline.stages_orchestrate import signal_of
from app.pipeline.tools_read import DENIED_REFUND, checked

# Config
REFUND_SECRET = "refund_database_url"
APPROVED = "approved"  # a refund the brain made is approved: S7 and, when needed, a human already cleared it
FULLY, PARTLY = "refunded", "partially_refunded"
REFUNDABLE = {"paid", PARTLY}  # an order in any other state (refunded, cancelled, disputed) is a human's call


def refunds_connection(lane) -> Connection | None:
    """The live shop database the brain may refund in: it has an order map and the refund user's address."""
    connection = orders_database(lane)  # by key, never by listing
    return connection if connection and REFUND_SECRET in connection.secrets_set else None


def refund_id(idempotency_key: str) -> str:
    """The same key always makes the same refund id, so the shop's primary key refuses a second refund for it."""
    return "RF-B-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16].upper()


def failed(code: str, retryable: bool) -> dict:
    return {"status": "failed", "external_ref": None, "summary": "", "error": {"code": code, "retryable": retryable}}


# --- Inside the one transaction

def lock_order(db: psycopg.Connection, m, payment_ref: str, customer: str) -> dict | None:
    """The customer's own order behind the payment, locked until commit, so a second worker waits and then sees this refund.
    None when there is no such payment, or it is someone else's: the run must not learn which."""
    row = db.execute(f"SELECT o.{checked(m.order_id)}, o.{checked(m.total_minor)}, o.{checked(m.currency)}, o.{checked(m.status)} FROM {checked(m.orders)} o "
                     f"JOIN {checked(m.customers)} c ON c.{checked(m.customer_id)} = o.{checked(m.order_customer)} WHERE o.{checked(m.payment_ref)} = %s "
                     f"AND (lower(c.{checked(m.customer_email)}) = lower(%s) OR c.{checked(m.customer_id)} = %s) FOR UPDATE OF o", (payment_ref, customer, customer)).fetchone()
    return dict(zip(("order_id", "total_minor", "currency", "status"), row)) if row else None


def refunded_so_far(db: psycopg.Connection, m, order_id: str) -> int:
    """Money already returned on the order, by anyone. A denied refund returned nothing."""
    row = db.execute(f"SELECT coalesce(sum({checked(m.refund_amount)}), 0) FROM {checked(m.refunds)} WHERE {checked(m.refund_order)} = %s "
                     f"AND {checked(m.refund_status)} <> %s", (order_id, DENIED_REFUND)).fetchone()
    return int(row[0])


def already_made(db: psycopg.Connection, m, rid: str) -> bool:
    return db.execute(f"SELECT 1 FROM {checked(m.refunds)} WHERE {checked(m.refund_id)} = %s", (rid,)).fetchone() is not None


def refusal(order: dict | None, amount: dict, refunded: int) -> str | None:
    """Why the shop's own data says no, checked at the moment of writing. None means the refund may go in."""
    if order is None:
        return "order_not_found"
    if amount["currency"] != order["currency"]:
        return "currency_mismatch"
    if order["status"] not in REFUNDABLE:
        return "order_not_refundable"
    if amount["amount_minor"] <= 0 or refunded + amount["amount_minor"] > order["total_minor"]:
        return "exceeds_paid"
    return None


def write_refund(db: psycopg.Connection, m, rid: str, order: dict, amount_minor: int, refunded: int, now) -> None:
    """Add the refund and set the order's status: fully refunded, or partly."""
    db.execute(f"INSERT INTO {checked(m.refunds)} ({checked(m.refund_id)}, {checked(m.refund_order)}, {checked(m.refund_amount)}, {checked(m.refund_status)}, "
               f"{checked(m.refund_created)}) VALUES (%s, %s, %s, %s, %s)", (rid, order["order_id"], amount_minor, APPROVED, now))
    status = FULLY if refunded + amount_minor >= order["total_minor"] else PARTLY
    db.execute(f"UPDATE {checked(m.orders)} SET {checked(m.status)} = %s WHERE {checked(m.order_id)} = %s", (status, order["order_id"]))


# --- The refund tool

def refund(lane, connection: Connection, arguments: dict, idempotency_key: str, customer: str) -> dict:
    """S9's call: one refund of the customer's own order, once. A busy or unreachable shop is retryable; the shop's data saying no is not."""
    m, rid, amount = connection.orders_map, refund_id(idempotency_key), arguments["amount"]
    try:
        with conn_db.open_refunds(lane, connection) as db:
            # Step 1: lock the order; a refund this key already made is the answer again
            order = lock_order(db, m, arguments["payment_ref"], customer)
            if order is not None and already_made(db, m, rid):
                count("s9.refund_replayed")
                return {"status": "succeeded", "external_ref": rid, "summary": f"refund {rid} was already made on order {order['order_id']}"}
            # Step 2: check against the shop's data now, then write; leaving the block commits
            refunded = refunded_so_far(db, m, order["order_id"]) if order else 0
            if reason := refusal(order, amount, refunded):
                count(f"s9.refund_refused.{reason}")
                return failed(reason, False)
            write_refund(db, m, rid, order, amount["amount_minor"], refunded, lane.now)
    except psycopg.OperationalError as error:  # down, timed out, or waiting too long for a lock: try again with the same key
        count("s9.shop_unavailable")
        log_event("S9", "shop_unavailable", connection_id=connection.connection_id, error=type(error).__name__)
        return failed("shop_unavailable", True)
    except (psycopg.Error, conn_db.NotAllowed) as error:  # no right, or the map is wrong: a setup problem for a person
        log_event("S9", "shop_refused", connection_id=connection.connection_id, error=type(error).__name__)
        return failed("shop_refused", False)
    count("s9.refunded")
    return {"status": "succeeded", "external_ref": rid, "summary": f"refunded {amount['currency']} {amount['amount_minor']} on order {order['order_id']}"}


def run_customer(lane, run) -> str | None:
    """How the shop knows this run's customer (email or its own id), from the run's latest message, as S5 and S7 read it."""
    signal = signal_of(lane, run.task.signal_ids[-1])
    return retrieve_case.customer_key(lane, signal.actor.ref if signal and signal.actor.type == "customer" else None)


def runner(lane, run):
    """S9's runner for this run's refunds: the shop's database when it gave a refund user. Without one, a lane built with a
    stand-in gateway (stage tests) uses it; production has none, so the refund fails and a person is told."""
    def run_refund(tool_id: str, arguments: dict, idempotency_key: str) -> dict:
        connection = refunds_connection(lane)
        if connection:
            customer = run_customer(lane, run)
            return refund(lane, connection, arguments, idempotency_key, customer) if customer else failed("customer_unknown", False)
        return lane.gateway(tool_id, arguments, idempotency_key) if lane.gateway else failed("no_refund_connection", False)
    return run_refund
