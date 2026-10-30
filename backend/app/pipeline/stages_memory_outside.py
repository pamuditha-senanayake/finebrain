# stages_memory_outside.py: work done outside Finebrain becomes living memory (stage 5c). Every refund, made by the brain
# or by a person in Stripe or the shop's admin, lands in the shop's own refunds table; the brain's own carry an RF-B- id.
# The others are read by a keyset cursor, checked against the refund policy in force that day, kept as outside traces,
# and published as K16, so they take the same triage path as runs. Polling is safe to repeat and one worker polls a shop
# at a time. Used by: conn_inbound.py (the polling loop), tests/test_memory_outside.py.
# Uses: stages_memory.py, stages_memory_flow.py (MATCH_KIND), conn_call.py, conn_db.py, tools_read.py (checked), stages_normalize.py (claim).
import time
from datetime import datetime, timezone

from pydantic import BaseModel

from app.pipeline import conn_db
from app.pipeline import stages_memory as memory
from app.pipeline.conn_call import Connection, orders_database
from app.pipeline.contracts_memory import PolicyCheck, TracePolicy
from app.pipeline.contracts_signal import VersionRef
from app.pipeline.observe import count, log_event
from app.pipeline.stages_memory_flow import MATCH_KIND
from app.pipeline.stages_normalize import claim
from app.pipeline.tools_read import checked

# Config
CURSOR_KIND = "memory_outside_cursor"  # records kind keyed by connection id: the last refund read
BRAIN_REFUND_PREFIX = "RF-B-"  # tools_write.refund_id: the brain's own refunds
POLICY_ID = "policy_refund"
AREA = "customer_care"
STEPS = ["refund_by_hand"]
BATCH = 200
POLL_SECONDS = 300
UNKNOWN_START = datetime(1970, 1, 1, tzinfo=timezone.utc)  # a policy node with no valid-from date
last_polled: dict[str, float] = {}  # connection id to monotonic time; in memory, so a restart polls at once


class OutsideCursor(BaseModel):
    at: datetime
    refund_id: str


class ShopRefund(BaseModel):
    refund_id: str
    amount_minor: int
    status: str
    created_at: datetime
    order_id: str
    paid_at: datetime
    currency: str


# --- Reading the shop

def read_refunds(db, connection: Connection, after: OutsideCursor | None, limit: int = BATCH) -> list[ShopRefund]:
    """Refunds made outside the brain, oldest first, strictly after the cursor. Every name is checked before it reaches SQL."""
    m = connection.orders_map
    where, args = ("AND (r.{c}, r.{i}) > (%s, %s)".format(c=checked(m.refund_created), i=checked(m.refund_id)), (after.at, after.refund_id)) if after else ("", ())
    rows = db.execute(
        f"""SELECT r.{checked(m.refund_id)}, r.{checked(m.refund_amount)}, r.{checked(m.refund_status)}, r.{checked(m.refund_created)},
                   o.{checked(m.order_id)}, o.{checked(m.paid_at)}, o.{checked(m.currency)}
            FROM {checked(m.refunds)} r JOIN {checked(m.orders)} o ON o.{checked(m.order_id)} = r.{checked(m.refund_order)}
            WHERE r.{checked(m.refund_id)} NOT LIKE %s {where}
            ORDER BY r.{checked(m.refund_created)}, r.{checked(m.refund_id)} LIMIT %s""",
        (BRAIN_REFUND_PREFIX + "%", *args, limit)).fetchall()
    return [ShopRefund(refund_id=r[0], amount_minor=r[1], status=r[2], created_at=r[3], order_id=r[4], paid_at=r[5], currency=r[6]) for r in rows]


# --- The policy check

def policy_in_force(lane, at: datetime) -> dict | None:
    """The refund policy version valid on that day: the newest whose valid-from has come; a version with no date counts as always."""
    versions = [v for v in lane.graph.history("policy", POLICY_ID) if not v.get("_closed")]
    dated = [v for v in versions if datetime.fromisoformat(v.get("valid_from", UNKNOWN_START.isoformat())) <= at]
    return dated[-1] if dated else None


def check_refund(refund: ShopRefund, policy: dict | None) -> tuple[PolicyCheck, list[str]]:
    """Inside the window or not, as S7 checks it; an amount over the automatic limit is noted, since a person may approve it."""
    if not policy:
        return "unknown", ["No refund policy in force that day"]
    days = (refund.created_at - refund.paid_at).days
    why = [f"{days} days since purchase, window is {policy['window_days']}"]
    limit = policy.get("auto_limit", {})
    if refund.currency == limit.get("currency") and refund.amount_minor > limit.get("amount_minor", refund.amount_minor):
        why.append(f"{refund.amount_minor} {refund.currency} is above the automatic limit of {limit['amount_minor']}, so a person had to approve it")
    return ("outside" if days > policy["window_days"] else "within"), why


def trace_of_refund(lane, refund: ShopRefund) -> memory.TraceRecord:
    policy = policy_in_force(lane, refund.created_at)
    check, why = check_refund(refund, policy)
    policies = [TracePolicy(policy_ref=VersionRef(**policy["_ref"]), valid_from=datetime.fromisoformat(policy.get("valid_from", UNKNOWN_START.isoformat())), valid_to=None)] if policy else []
    trace = memory.trace_of_outside(lane.seed["tenant_id"], f"shop-{refund.refund_id}", AREA, refund.created_at, STEPS, f"refunded by a person ({refund.status})", check, policies)
    return trace.model_copy(update={"why": why})


# --- Polling

def poll_refunds(lane, limit: int = BATCH) -> int:
    """One pass over the shop's new refunds. Returns how many new outside traces it kept. One worker per shop at a time."""
    connection = orders_database(lane)
    if connection is None or not claim(lane.memory_claims, f"outside:{connection.connection_id}"):
        return 0
    try:
        return take_refunds(lane, connection, limit)
    finally:
        lane.memory_claims.discard(f"outside:{connection.connection_id}")


def take_refunds(lane, connection: Connection, limit: int) -> int:
    # Step 1: read after the saved cursor, read only, and let the transaction go
    saved = lane.records.load(CURSOR_KIND, connection.connection_id)
    with conn_db.open_read_only(lane, connection) as db:
        refunds = read_refunds(db, connection, OutsideCursor(**saved) if saved else None, limit)
        db.rollback()
    # Step 2: keep each as a trace; publish when first kept, or again if it was never triaged (a crash in between)
    kept = 0
    for refund in refunds:
        trace = trace_of_refund(lane, refund)
        first = lane.traces.save(trace)
        kept += first
        if first or not lane.records.load(MATCH_KIND, trace.trace_id):
            lane.bus.publish("traces.recorded", "trace.recorded", lane.traces.get(trace.trace_id), "memory")
    # Step 3: move the cursor only after the traces are kept, so a crash re-reads rather than skips
    if refunds:
        lane.records.save(CURSOR_KIND, connection.connection_id, OutsideCursor(at=refunds[-1].created_at, refund_id=refunds[-1].refund_id))
    count("memory.outside_kept", kept)
    return kept


def poll_due(lane) -> None:
    """Called from the polling loop. Polls the shop every POLL_SECONDS; a failure is counted and logged, never raised."""
    connection = orders_database(lane) if lane.traces is not None else None
    if connection is None or time.monotonic() - last_polled.get(connection.connection_id, 0) < POLL_SECONDS:
        return
    last_polled[connection.connection_id] = time.monotonic()
    try:
        poll_refunds(lane)
    except Exception as error:  # one catch for the loop's entry point: the next pass tries again
        count("memory.outside_poll_failed")
        log_event("memory", "outside_poll_failed", connection_id=connection.connection_id, error=type(error).__name__)
