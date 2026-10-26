# test_s9_real.py: S9 Act for the refund BDD, against the real shop database (finebase_shop on Postgres). Anna's chat is
# one connected conversation: she asks (no money moves), confirms (the refund row and the order's status are in the shop),
# then asks again after the run closed (nothing is refunded twice). Then the same on Postgres, Valkey, Redpanda and S3,
# and the graph's tool node deciding where the refund goes. Lines: "the refund is issued to the original payment method",
# "the order shows refunded". Uses: tools_write.py, run_finish.py, tests/s7_world.py, tests/s6_world.py, scripts/shop_db.py.
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from app.pipeline import conn_call, observe, orchestrate, tools_write
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.contracts_run import Decision
from app.pipeline.kafka_admin import delete_prefixed_topics
from app.pipeline.store_graph import SEED_COMMIT
from scripts import shop_db
from tests.s5_world import connect_shop, needs_postgres
from tests.s6_world import ask, refund, scripted
from tests.s7_world import actions, full_lane, last_record, runs, says
from tests.test_s1_real import read_topic
from tests.test_s1_refund_chat import FIRST, SECOND
from tests.test_s5_real import S5_PARTS, parts
from tests.test_s7_s10_real import seed_for

pytestmark = needs_postgres

# Config
THIRD = {"id": "chat_msg_anna_3", "text": "Can you refund the mouse again please?"}
MOUSE_ORDER = "ORD-1002"


def shop(sql: str, *params) -> list[tuple]:
    """Read the shop as its own staff would, to see what the brain really wrote."""
    with psycopg.connect(shop_db.owner_url()) as db:
        return db.execute(sql, params).fetchall()


def brain_refunds(order_id: str = MOUSE_ORDER) -> list[tuple]:
    return shop("SELECT id, amount_minor, status FROM shop.refunds WHERE order_id = %s AND id LIKE 'RF-B-%%' ORDER BY id", order_id)


def order_status(order_id: str = MOUSE_ORDER) -> str:
    return shop("SELECT status FROM shop.orders WHERE id = %s", order_id)[0][0]


# --- BDD: every visit of Anna's chat

def test_visit_1_asks_first_and_no_money_moves():
    lane = full_lane()
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    assert last_record(lane)["outcome"] == "awaiting_customer"
    assert brain_refunds() == [] and order_status() == "paid"


def test_visit_2_refunds_in_the_shop_and_the_order_shows_refunded():
    lane = full_lane()
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    says(lane, SECOND)
    result = lane.bus.topics["actions.executed"][-1].payload
    expected_id = tools_write.refund_id(result["idempotency_key"])
    assert brain_refunds() == [(expected_id, 400000, "approved")] and order_status() == "refunded"
    assert (result["status"], result["external_ref"]) == ("succeeded", expected_id)  # K9 points at the shop's own row
    assert shop("SELECT created_at FROM shop.refunds WHERE id = %s", expected_id)[0][0] == lane.now
    assert (last_record(lane)["outcome"], last_record(lane)["decided_by"]) == ("resolved", "auto by policy")


def test_visit_3_after_the_run_closed_never_refunds_twice():
    lane = full_lane()
    lane.model, _ = scripted(ask(), refund(), refund())
    says(lane, FIRST)
    says(lane, SECOND)
    says(lane, THIRD)
    assert len(brain_refunds()) == 1 and order_status() == "refunded"
    assert [status for tool, status in actions(lane) if tool == "tool_payment_refund"] == ["succeeded"]  # S7 stopped the second one before S9
    assert list(runs(lane).values()) == [["awaiting_customer", "resolved"], ["escalated"]]  # a new run, handed to a person


def test_a_refund_in_another_currency_than_the_limit_waits_for_a_person_then_lands():
    lane = full_lane()
    lane.now = lane.bus.now = datetime(2026, 10, 26, 9, tzinfo=timezone.utc)
    gateway = {"payment_ref": "pay_FB_20261015_0482", "amount": {"amount_minor": 12900, "currency": "USD"}, "citations": ["order:ORD-10482", "item_policy_window"]}
    lane.model, _ = scripted(ask(citations=["order:ORD-10482"]), refund(**gateway))
    amara = {"email": "amara.fernando@northwind.io", "session": "chat_sess_amara", "name": "Amara"}
    says(lane, {"id": "msg_amara_1", "text": "I want a refund for my last order"}, **amara)
    says(lane, {"id": "msg_amara_2", "text": "yes, that one"}, **amara)
    assert last_record(lane)["outcome"] == "awaiting_approval" and brain_refunds("ORD-10482") == []  # USD 129 is not under an LKR limit
    approval = lane.bus.topics["approvals.requested"][-1].payload
    orchestrate.decide(lane, Decision(approval_id=approval["approval_id"], decision="approve", decided_by=["head_of_cs"], decided_at=lane.now))
    lane.bus.drain()
    assert [r[1:] for r in brain_refunds("ORD-10482")] == [(12900, "approved")] and order_status("ORD-10482") == "refunded"


# --- The graph decides where the refund goes

def test_a_studio_edit_of_the_tool_endpoint_is_what_s9_does():
    lane = full_lane()
    node = {"studio": {"id": "tool:issue_refund", "kind": "tool", "fields": {"endpoint": "shop_database"}}}
    lane.graph.put("tool", "tool:issue_refund", 2, SEED_COMMIT, node)
    lane.graph.put("tool", "tool:issue_refund", 3, "cmt_studio_edit", {"studio": {**node["studio"], "fields": {"endpoint": "old_gateway"}}})
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    says(lane, SECOND)
    assert actions(lane)[-1] == ("tool_payment_refund", "failed") and last_record(lane)["outcome"] == "failed"  # a person is told
    assert lane.bus.topics["actions.executed"][-1].payload["error"]["code"] == "no_runner" and brain_refunds() == []


def test_without_a_refund_user_nothing_is_refunded_and_a_person_is_told():
    lane = full_lane()
    lane.gateway = None  # as in production: no stand-in
    connect_shop(lane, refunds=False)
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    says(lane, SECOND)
    assert lane.bus.topics["actions.executed"][-1].payload["error"]["code"] == "no_refund_connection"
    assert last_record(lane)["outcome"] == "failed" and brain_refunds() == []


# --- The shop database is found by key

def test_a_whole_refund_chat_never_lists_the_connections(monkeypatch):
    lane = full_lane()
    monkeypatch.setattr(conn_call, "all_connections", lambda lane: (_ for _ in ()).throw(AssertionError("listed every connection")))
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    says(lane, SECOND)
    assert len(brain_refunds()) == 1 and order_status() == "refunded"


def test_pausing_the_shop_clears_its_role_and_switching_it_back_restores_it():
    lane = full_lane()
    shop = conn_call.load(lane, "conn_shop_db")
    conn_call.save(lane, shop.model_copy(update={"status": "paused"}))
    assert tools_write.refunds_connection(lane) is None
    conn_call.save(lane, shop)
    assert tools_write.refunds_connection(lane).connection_id == "conn_shop_db"


def test_pausing_one_of_two_shop_databases_hands_the_role_to_the_other():
    lane = full_lane()
    first = conn_call.load(lane, "conn_shop_db")
    second = conn_call.save(lane, first.model_copy(update={"connection_id": "conn_shop_db_2"}))
    conn_call.save(lane, second.model_copy(update={"status": "paused"}))
    assert conn_call.orders_database(lane).connection_id == tools_write.refunds_connection(lane).connection_id == "conn_shop_db"  # the first still serves


# --- The same chat on real infra

@pytest.mark.skipif(bool(missing_infra(S5_PARTS)), reason="infra not answering")
def test_anna_is_refunded_in_the_shop_on_real_infra():
    tag = uuid.uuid4().hex[:8]
    observe.reset_counts()
    lane = full_lane(real_adapters(parts(), topic_prefix=f"s9{tag}."), seed=seed_for(tag))
    try:
        lane.model, _ = scripted(ask(), refund())
        says(lane, FIRST)
        says(lane, SECOND)
        refunded = [m["payload"] for m in read_topic(f"s9{tag}.actions.executed", 2)][-1]  # from Redpanda
        assert brain_refunds() == [(refunded["external_ref"], 400000, "approved")] and order_status() == "refunded"
        assert lane.tooling["results"].get(refunded["idempotency_key"])["external_ref"] == refunded["external_ref"]  # from Valkey
        assert lane.records.load("run", refunded["run_id"])["outcome"] == "resolved"  # from Postgres
    finally:
        delete_prefixed_topics(f"s9{tag}.")
