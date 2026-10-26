# test_s5_access_time.py: S5 picks the right version of the truth, shows each reader only what they may see, keeps every
# customer apart, and degrades when the shop's database fails, never guessing. Real shop database (Postgres, read-only user).
# Uses: retrieve_case.py, tools_read.py, stages_retrieve.py, conn_spec.py (OrderMap), tests/s5_world.py, scripts/shop_db.py.
from datetime import datetime

import psycopg
import pytest

from app.pipeline import observe
from app.pipeline.conn_spec import OrderMap
from scripts import shop_db
from tests.s5_world import ask, connect_shop, ids, make_lane, needs_postgres, query_for, text_of, visitor_says
from tests.test_s1_refund_chat import FIRST

pytestmark = needs_postgres

# Config
CURRENT_POLICY_IDS = {"item_policy_window", "item_policy_auto_limit", "item_policy_late_large"}
WINDOWS = {"item_policy_window_v1": "7 days", "item_policy_window_v2": "14 days", "item_policy_window": "30 days", "item_policy_window_v4": "45 days"}


def at(day: str) -> datetime:
    return datetime.fromisoformat(f"{day}T12:00:00+05:30")


@pytest.fixture
def anna():
    lane = make_lane()
    return lane, visitor_says(lane, FIRST)


def windows(bundle) -> list[str]:
    return sorted(ids(bundle) & set(WINDOWS))


# --- The right version for the asked time

@pytest.mark.parametrize("day, window, limit", [
    ("2024-06-01", "item_policy_window_v1", None),  # the 7 day window; no limit was written down yet
    ("2025-06-01", "item_policy_window_v2", "item_policy_auto_limit_v2"),  # 14 days, LKR 25,000
    ("2026-10-10", "item_policy_window", "item_policy_auto_limit"),  # today: 30 days, LKR 50,000
    ("2026-11-15", "item_policy_window_v4", "item_policy_auto_limit"),  # the 45 day window, once it starts
])
def test_each_time_gets_exactly_its_own_policy_version(anna, day, window, limit):
    lane, task = anna
    bundle, _ = ask(lane, query_for(lane, task, as_of_valid=at(day)))
    assert windows(bundle) == [window]  # never two windows at once, never a future one
    assert limit is None or limit in ids(bundle)


def test_orders_and_refunds_are_as_they_were_at_the_asked_time(anna):
    lane, task = anna
    before_refund, _ = ask(lane, query_for(lane, task, as_of_valid=at("2026-07-05")))
    after_refund, _ = ask(lane, query_for(lane, task, as_of_valid=at("2026-08-01")))
    assert ids(before_refund) & {"order:ORD-1001", "order:ORD-1002"} == {"order:ORD-1001"}  # the mouse was not bought yet
    assert "no refund yet" in text_of(before_refund, "order:ORD-1001") and "refunded LKR 18,500.00" in text_of(after_refund, "order:ORD-1001")


def test_a_refund_the_shop_records_shows_on_the_next_read(anna):
    lane, task = anna
    with psycopg.connect(shop_db.owner_url(), autocommit=True) as shop:  # the shop's staff refund the mouse in their own system
        shop.execute("INSERT INTO shop.refunds VALUES ('RF-0002', 'ORD-1002', 400000, 'approved', '2026-10-10T09:00:00+05:30')")
    bundle, _ = ask(lane, query_for(lane, task))
    assert "refunded LKR 4,000.00 so far" in text_of(bundle, "order:ORD-1002")  # read fresh, never a stale copy


# --- Who may read what

def test_an_agent_without_the_right_to_read_gets_nothing(anna):
    lane, task = anna
    bundle, decision = ask(lane, query_for(lane, task, agent_id="agent_greeter"))
    assert bundle.items == [] and decision.decision == "deny" and decision.rule_id == "capability_kb_read"
    assert observe.read_count("s5.denied.no_capability") == 1


def test_the_restricted_note_is_withheld_from_l3_and_shown_to_l2(anna):
    lane, task = anna
    l3, _ = ask(lane, query_for(lane, task))
    l2, _ = ask(lane, query_for(lane, task, agent_id="agent_risk_reviewer"))
    assert "item_fraud_watch" not in ids(l3) and l3.denied_count == 1
    assert "item_fraud_watch" in ids(l2) and l2.denied_count == 0


def test_acting_for_a_person_reads_only_what_both_may(anna):
    lane, task = anna
    for_l3, _ = ask(lane, query_for(lane, task, agent_id="agent_risk_reviewer", on_behalf_of="support_operator_1"))
    for_nobody, _ = ask(lane, query_for(lane, task, on_behalf_of="person_not_in_the_directory"))
    assert "item_fraud_watch" not in ids(for_l3) and "order:ORD-1002" in ids(for_l3)  # L3 may read orders, not restricted notes
    assert for_nobody.items == [] and for_nobody.denied_count > 0  # an unknown person reads nothing, and it is counted


# --- Every customer sees only their own orders

@pytest.mark.parametrize("email, session, orders", [
    ("ben@example.lk", "chat_sess_ben", ["order:ORD-2001"]),
    ("chen@example.lk", "chat_sess_chen", []),  # a customer with no orders: policies only
    ("dee@example.lk", "chat_sess_dee", ["order:ORD-3001"]),
    (None, "chat_sess_guest", []),  # an anonymous visitor: nothing behind their token
])
def test_each_customer_sees_only_their_own_orders(email, session, orders):
    lane = make_lane()
    task = visitor_says(lane, {"id": f"msg_{session}", "text": "I want a refund for my last order"}, email=email, session=session, name="Visitor")
    bundle, _ = ask(lane, query_for(lane, task))
    assert sorted(i for i in ids(bundle) if i.startswith("order:")) == orders


def test_a_customer_key_that_tries_sql_finds_nothing(anna):
    lane, task = anna
    lane.vault["pii_tok_injection_try"] = "x' OR '1'='1"
    bundle, _ = ask(lane, query_for(lane, task, customer_ref="pii_tok_injection_try"))
    assert not [i for i in ids(bundle) if i.startswith("order:")]  # the key is a parameter, so it matched no customer


# --- Unhappy paths: no orders, never a guess, never a crash

def test_the_shop_database_down_still_gives_the_policies(anna):
    lane, task = anna
    connect_shop(lane, url=shop_db.reader_url().replace(":5433/", ":5999/"))  # nothing listens there
    bundle, decision = ask(lane, query_for(lane, task))
    assert CURRENT_POLICY_IDS <= ids(bundle) and not [i for i in ids(bundle) if i.startswith("order:")]
    assert "orders unavailable" in decision.reason and observe.read_count("s5.orders_unavailable") == 1


def test_a_wrong_password_is_handled_like_an_outage(anna):
    lane, task = anna
    connect_shop(lane, url=shop_db.reader_url().replace("test-only-shop-reader", "wrong"))
    _, decision = ask(lane, query_for(lane, task))
    assert "orders unavailable" in decision.reason


def test_a_map_that_carries_sql_is_refused_before_the_database(anna):
    lane, task = anna
    connect_shop(lane, orders_map=OrderMap(orders="shop.orders; DROP TABLE shop.orders"))
    _, decision = ask(lane, query_for(lane, task))
    assert "orders unavailable" in decision.reason
    with psycopg.connect(shop_db.owner_url()) as shop:
        assert shop.execute("SELECT count(*) FROM shop.orders").fetchone()[0] == len(shop_db.WORLD["orders"])  # nothing reached the shop


def test_a_paused_connection_is_not_read(anna):
    lane, task = anna
    connect_shop(lane, status="paused")
    _, decision = ask(lane, query_for(lane, task))
    assert "no shop or no customer" in decision.reason

