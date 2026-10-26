# test_s9_rules.py: the refund tool's rules on the real shop database. Once per key (retries, two workers at once), never
# more than was paid (two runs at once, partial refunds), the shop's data saying no, a down or busy shop retried with the
# same key, and users with exactly the rights they need (the connection test proves it, Postgres enforces it).
# Uses: tools_write.py, stages_act.py, conn_db.py, conn_test.py, api/connect_brief.py, tests/s7_world.py, scripts/shop_db.py.
import threading

import psycopg
import pytest

from app.api import connect_brief
from app.pipeline import conn_call, conn_test, stages_act, tools_write
from app.pipeline.conn_call import Connection
from app.pipeline.conn_spec import Need
from scripts import shop_db
from tests.s5_world import SHOP, needs_postgres
from tests.s7_world import full_lane
from tests.test_act import EXECUTE, REFUND, tooling
from tests.test_s9_real import brain_refunds, order_status

pytestmark = needs_postgres

# Config
MOUSE = {"payment_ref": "pay_FB_20260930_0144", "reason_code": "within_window_full"}
DOWN_URL = "postgresql://brain_shop_refunder:x@127.0.0.1:1/finebase_shop"


def lane_and_shop():
    lane = full_lane()
    return lane, tools_write.refunds_connection(lane)


def pay_back(lane, connection, key: str, amount_minor: int = 400000, currency: str = "LKR", payment_ref: str = MOUSE["payment_ref"], customer: str = "anna@example.lk") -> dict:
    return tools_write.refund(lane, connection, {**MOUSE, "payment_ref": payment_ref, "amount": {"amount_minor": amount_minor, "currency": currency}}, key, customer)


def at_once(*calls) -> list:
    """Run the calls on threads that start together, as two workers would."""
    results, start = [None] * len(calls), threading.Barrier(len(calls))
    def run(index, call):
        start.wait()
        results[index] = call()
    threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


# --- Once per key, never more than was paid

def test_a_retry_with_the_same_key_gives_the_same_refund():
    lane, shop = lane_and_shop()
    first, again = pay_back(lane, shop, "k:run_1:step_1"), pay_back(lane, shop, "k:run_1:step_1")
    assert first["external_ref"] == again["external_ref"] and again["status"] == "succeeded" and len(brain_refunds()) == 1


def test_two_workers_with_the_same_key_make_one_refund():
    lane, shop = lane_and_shop()
    results = at_once(*[lambda: pay_back(lane, shop, "k:run_1:step_1")] * 2)
    assert [r["status"] for r in results] == ["succeeded"] * 2 and len({r["external_ref"] for r in results}) == 1 and len(brain_refunds()) == 1


def test_two_runs_at_once_on_one_order_never_return_more_than_was_paid():
    lane, shop = lane_and_shop()
    results = at_once(lambda: pay_back(lane, shop, "k:run_1:s"), lambda: pay_back(lane, shop, "k:run_2:s"))
    assert sorted(r["status"] for r in results) == ["failed", "succeeded"] and len(brain_refunds()) == 1
    assert next(r for r in results if r["status"] == "failed")["error"] == {"code": "order_not_refundable", "retryable": False}  # it waited, then saw "refunded"


def test_partial_refunds_add_up_and_set_the_status_on_the_way():
    lane, shop = lane_and_shop()
    assert pay_back(lane, shop, "k:a", 150000)["status"] == "succeeded" and order_status() == "partially_refunded"
    assert pay_back(lane, shop, "k:b", 250000)["status"] == "succeeded" and order_status() == "refunded"
    assert pay_back(lane, shop, "k:c", 1)["error"]["code"] == "order_not_refundable"


@pytest.mark.parametrize("change, code", [({"currency": "USD"}, "currency_mismatch"), ({"payment_ref": "pay_FB_20990101_0001"}, "order_not_found"),
                                          ({"amount_minor": 0}, "exceeds_paid"), ({"amount_minor": 400001}, "exceeds_paid"),
                                          ({"payment_ref": "pay_FB_20260702_0101", "amount_minor": 1}, "order_not_refundable"),
                                          ({"customer": "ben@example.lk"}, "order_not_found"), ({"customer": "cus_ben"}, "order_not_found")])
def test_the_shops_own_data_says_no_and_nothing_is_written(change, code):
    lane, shop = lane_and_shop()
    assert pay_back(lane, shop, "k:bad", **change)["error"] == {"code": code, "retryable": False}
    assert brain_refunds_anywhere() == 0


def brain_refunds_anywhere() -> int:
    with psycopg.connect(shop_db.owner_url()) as db:
        return db.execute("SELECT count(*) FROM shop.refunds WHERE id LIKE 'RF-B-%'").fetchone()[0]


def test_the_shops_own_customer_id_finds_her_order_like_her_email():
    lane, shop = lane_and_shop()
    assert pay_back(lane, shop, "k:by_id", customer="cus_anna")["status"] == "succeeded" and len(brain_refunds()) == 1


# --- A down or busy shop: retried with the same key, then a person is told

def test_a_shop_that_is_down_is_retried_then_the_run_fails_for_a_person():
    lane, shop = lane_and_shop()
    conn_call.save(lane, conn_call.set_secret(lane, shop, "refund_database_url", DOWN_URL))
    tools, sleeps = tooling(), []
    tools.update(runners={"shop_database": lambda tool_id, arguments, key: tools_write.refund(lane, shop, arguments, key, "anna@example.lk")}, sleep=sleeps.append)
    result = stages_act.act(REFUND.model_copy(update={"arguments": {**MOUSE, "amount": {"amount_minor": 400000, "currency": "LKR"}}}), EXECUTE, None, "t", tools, lane.new_id, lane.now)
    assert (result.status, result.error.code, result.error.retryable) == ("failed", "shop_unavailable", True)
    assert len(sleeps) == stages_act.ATTEMPTS - 1 and brain_refunds() == []


def test_a_lock_held_by_the_shop_is_waited_for_then_the_same_key_succeeds():
    lane, shop = lane_and_shop()
    with psycopg.connect(shop_db.owner_url()) as staff:
        staff.execute("SELECT 1 FROM shop.orders WHERE id = 'ORD-1002' FOR UPDATE")
        assert pay_back(lane, shop, "k:busy")["error"] == {"code": "shop_unavailable", "retryable": True}
        staff.rollback()
    assert pay_back(lane, shop, "k:busy")["status"] == "succeeded" and len(brain_refunds()) == 1


# --- Exactly the rights a refund needs

def test_the_connection_test_passes_the_refund_user_and_writes_nothing():
    lane, shop = lane_and_shop()
    lines, _ = conn_test.run_test(lane, shop)
    assert next(line for line in lines if line["item"] == "Refund user")["ok"] is True and brain_refunds_anywhere() == 0


@pytest.mark.parametrize("grant, who, line", [("GRANT DELETE ON shop.refunds TO brain_shop_refunder", "refund", "Refund user"),
                                              ("GRANT UPDATE (total_minor) ON shop.orders TO brain_shop_refunder", "refund", "Refund user"),
                                              ("GRANT UPDATE (status) ON shop.orders TO brain_shop_reader", "read", "Read only")])
def test_a_user_with_one_right_too_many_fails_the_test(grant, who, line):
    lane, shop = lane_and_shop()
    with psycopg.connect(shop_db.owner_url(), autocommit=True) as owner:
        owner.execute(grant)
    lines, _ = conn_test.run_test(lane, shop)
    shop_db.setup()  # the schema is rebuilt, so the extra right is gone for the next test
    assert next(item for item in lines if item["item"] == line)["ok"] is False


@pytest.mark.parametrize("sql", ["DELETE FROM shop.refunds", "UPDATE shop.orders SET total_minor = 1", "INSERT INTO shop.customers VALUES ('x', 'x@x', 'x')"])
def test_postgres_refuses_the_refund_user_anything_else(sql):
    with psycopg.connect(shop_db.refunder_url()) as db, pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(sql)


def test_the_brief_asks_for_the_refund_user_and_its_answer_keeps_both_addresses_apart():
    connection = Connection(connection_id=SHOP, name="shop", kind="database", created_by="h", needs=[Need(name="refund_file", text="File a refund", writes=True)])
    assert "brain_refunder" in connect_brief.connect_brief_db.brief(connection, "Finebase")
    _, secrets, _ = connect_brief.read_answer('```brain-connection\n{"database": {"engine": "postgres", "schemas": ["shop"]}}\n```\n'
                                              "database_url: postgresql://r:1@h/db\nrefund_database_url: postgresql://w:2@h/db")
    assert secrets == {"database_url": "postgresql://r:1@h/db", "refund_database_url": "postgresql://w:2@h/db"}
