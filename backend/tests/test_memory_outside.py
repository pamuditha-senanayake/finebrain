# test_memory_outside.py: stage 5c of the living memory. Refunds people make by hand (in Stripe or the shop's admin) land in
# the shop's refunds table; the memory reads them by cursor, checks each against the refund policy in force that day, and
# keeps it as an outside trace that takes the triage path. The policy check runs without a database; the rest uses the real
# shop database from scripts/shop_db.py and skips when Postgres is down.
# Uses: app/pipeline/stages_memory_outside.py, tests/s5_world.py, scripts/shop_db.py.
from datetime import datetime, timedelta, timezone

import psycopg

from app.pipeline import stages_memory_outside as outside
from scripts import shop_db
from tests.s5_world import make_lane, needs_postgres

# Config
POLICY = {"window_days": 30, "auto_limit": {"amount_minor": 5000000, "currency": "LKR"}, "_ref": {"id": "policy_refund", "version": 3, "branch": "main", "commit_id": "c"}}
PAID = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def refund(days_after: int, amount: int = 1200000, refund_id: str = "RF-900") -> outside.ShopRefund:
    return outside.ShopRefund(refund_id=refund_id, amount_minor=amount, status="approved", created_at=PAID + timedelta(days=days_after),
                              order_id="ORD-9", paid_at=PAID, currency="LKR")


def shop_refund(order_id: str, refund_id: str, paid_days_ago: int, amount: int = 1200000) -> None:
    """A person refunds by hand, the way the shop's staff would: straight into the shop's own tables."""
    now = datetime.now(timezone.utc)
    with psycopg.connect(shop_db.owner_url(), autocommit=True) as shop:
        shop.execute("INSERT INTO shop.orders VALUES (%s, 'cus_anna', 'Desk lamp', %s, 'LKR', 'refunded', %s, %s)", (order_id, amount, now - timedelta(days=paid_days_ago), f"pay_{order_id}"))
        shop.execute("INSERT INTO shop.refunds VALUES (%s, %s, %s, 'approved', %s)", (refund_id, order_id, amount, now))


# --- The policy check, no database

def test_a_refund_inside_the_window_is_within_policy():
    assert outside.check_refund(refund(12), POLICY) == ("within", ["12 days since purchase, window is 30"])


def test_a_late_refund_is_outside_policy_and_says_why():
    check, why = outside.check_refund(refund(41, amount=8500000), POLICY)
    assert check == "outside" and why[0] == "41 days since purchase, window is 30" and "above the automatic limit" in why[1]


def test_with_no_policy_in_force_the_check_is_unknown():
    assert outside.check_refund(refund(5), None)[0] == "unknown"


# --- On the real shop database

@needs_postgres
def test_hand_refunds_become_outside_traces_once_and_the_brains_own_are_skipped():
    lane = make_lane()
    # Step 1: a late refund by hand, and one the brain made, join the sample refunds
    shop_refund("ORD-LATE", "RF-HAND-1", paid_days_ago=45)
    shop_refund("ORD-BRAIN", "RF-B-0000000000000001", paid_days_ago=3)
    kept = outside.poll_refunds(lane)
    lane.bus.drain()
    # Step 2: every hand refund is a trace, the late one is outside policy, the brain's own is not a trace
    late = lane.traces.get("tr-shop-RF-HAND-1")
    assert kept >= 2 and late.source == "outside" and late.policy_check == "outside" and late.why[0].startswith("45 days since purchase")
    assert late.policies and late.policies[0].policy_ref.id == "policy_refund"
    assert lane.traces.get("tr-shop-RF-B-0000000000000001") is None
    assert any(m.payload["trace_id"] == "tr-shop-RF-HAND-1" for m in lane.bus.topics["traces.matched"])
    # Step 3: the cursor moved, so a second pass keeps nothing new
    assert outside.poll_refunds(lane) == 0


@needs_postgres
def test_a_shop_another_worker_is_polling_is_left_alone():
    lane = make_lane()
    lane.memory_claims.add(f"outside:{outside.orders_database(lane).connection_id}")
    assert outside.poll_refunds(lane) == 0 and lane.traces.page("customer_care")[0] == []


@needs_postgres
def test_a_crash_before_the_cursor_moves_rereads_and_keeps_nothing_twice():
    lane = make_lane()
    first = outside.poll_refunds(lane)
    lane.records.purge(outside.CURSOR_KIND, outside.orders_database(lane).connection_id)  # as if the worker died before step 3
    assert first > 0 and outside.poll_refunds(lane) == 0
