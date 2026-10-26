# tools_read.py: read tools, the brain's way to look at a connected system's data. Today one: a customer's recent orders
# with their refunds, from a shop database. Every read goes through conn_db.py (one SELECT, read-only transaction, time
# limit, row cap) as the read-only user the shop gave; table and column names come from the connection's OrderMap.
# Used by: retrieve_case.py (S5). Uses: conn_db.py, conn_call.py, conn_spec.py (OrderMap), observe.py.
import re
from datetime import datetime

from app.pipeline import conn_db
from app.pipeline.conn_call import Connection, orders_database
from app.pipeline.conn_spec import OrderMap

# Config
ORDERS_SHOWN = 5  # the latest orders are what a refund needs; older ones stay in the shop
SAFE_NAME = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")
DENIED_REFUND = "denied"  # a denied refund returned no money


class ReadUnavailable(Exception):
    """The shop's database could not be read. S5 goes on without the orders and says so."""
    retryable = True


def checked(name: str) -> str:
    """A table or column name from the map, refused unless it is a plain name, so the map cannot carry SQL."""
    if not SAFE_NAME.match(name):
        raise conn_db.NotAllowed(f"Not a plain table or column name: {name}")
    return name


def orders_connection(lane) -> Connection | None:
    """The live shop database whose orders the brain may read, if the tenant has one. Read by key, never by listing."""
    return orders_database(lane)


# --- SQL built from the map

def orders_sql(m: OrderMap) -> str:
    """A customer's latest orders, by their email or the shop's own customer id. The key is a parameter, never part of the text."""
    o, c = checked(m.orders), checked(m.customers)
    columns = ", ".join(f"o.{checked(col)} AS {alias}" for col, alias in (
        (m.order_id, "order_id"), (m.product, "product"), (m.total_minor, "total_minor"), (m.currency, "currency"),
        (m.status, "status"), (m.paid_at, "paid_at"), (m.payment_ref, "payment_ref")))
    return (f"SELECT {columns} FROM {o} o JOIN {c} c ON c.{checked(m.customer_id)} = o.{checked(m.order_customer)} "
            f"WHERE lower(c.{checked(m.customer_email)}) = lower(%s) OR c.{checked(m.customer_id)} = %s ORDER BY o.{checked(m.paid_at)} DESC LIMIT {ORDERS_SHOWN}")


def refunds_sql(m: OrderMap) -> str:
    """Every refund on the given orders."""
    return (f"SELECT r.{checked(m.refund_order)} AS order_id, r.{checked(m.refund_amount)} AS amount_minor, r.{checked(m.refund_status)} AS status, "
            f"r.{checked(m.refund_created)} AS created_at FROM {checked(m.refunds)} r WHERE r.{checked(m.refund_order)} = ANY(%s)")


# --- The read tool

def find_customer_orders(lane, connection: Connection, customer: str) -> list[dict]:
    """The customer's latest orders, newest first, each with its refunds. A down or refusing database is ReadUnavailable."""
    try:
        orders = conn_db.read(lane, connection, orders_sql(connection.orders_map), (customer, customer))
        refunds = conn_db.read(lane, connection, refunds_sql(connection.orders_map), ([o["order_id"] for o in orders],)) if orders else []
    except conn_db.NotAllowed:
        raise  # a map S5 refused is a setup mistake to report, not an outage
    except Exception as error:  # the shop being down must not stop the run; S5 reports what it could not read
        raise ReadUnavailable(type(error).__name__) from None
    for order in orders:
        order["refunds"] = sorted((r for r in refunds if r["order_id"] == order["order_id"]), key=lambda r: r["created_at"])
    return sorted(orders, key=lambda o: o["paid_at"], reverse=True)  # the wrapping SELECT does not keep the order


def find_payment(lane, connection: Connection, payment_ref: str, customer: str) -> dict | None:
    """One payment as S7 checks it now: paid when, how much, refunded how much. Only when it is this customer's; else None."""
    m = connection.orders_map
    sql = (f"SELECT o.{checked(m.order_id)} AS order_id, o.{checked(m.total_minor)} AS total_minor, o.{checked(m.paid_at)} AS paid_at, o.{checked(m.status)} AS status "
           f"FROM {checked(m.orders)} o JOIN {checked(m.customers)} c ON c.{checked(m.customer_id)} = o.{checked(m.order_customer)} "
           f"WHERE o.{checked(m.payment_ref)} = %s AND (lower(c.{checked(m.customer_email)}) = lower(%s) OR c.{checked(m.customer_id)} = %s)")
    try:
        rows = conn_db.read(lane, connection, sql, (payment_ref, customer, customer))
        refunds = conn_db.read(lane, connection, refunds_sql(m), ([rows[0]["order_id"]],)) if rows else []
    except conn_db.NotAllowed:
        raise
    except Exception as error:
        raise ReadUnavailable(type(error).__name__) from None
    if not rows:
        return None
    order = {**rows[0], "refunds": refunds}
    return {"order_id": order["order_id"], "paid_at": order["paid_at"].isoformat(), "amount_minor": order["total_minor"], "refunded_minor": refunded_minor(order), "status": order["status"]}


def refunded_minor(order: dict, as_of: datetime | None = None) -> int:
    """Money already returned on an order, counting only refunds made by `as_of`."""
    return sum(r["amount_minor"] for r in order["refunds"] if r["status"] != DENIED_REFUND and (as_of is None or r["created_at"] <= as_of))
