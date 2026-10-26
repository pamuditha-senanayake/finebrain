# test_s5_retrieve_bdd.py: S5 Retrieve on its own, for the refund BDD. Anna's message runs through the real S1 to S3;
# the test asks S5 with the K4 that S4's run builds. Her orders come from a real shop database (Postgres, read-only user).
# Lines: "the Refund agent finds Anna's latest order", "the Refund agent checks the policy", "the order is inside
# 30 days, under the limit, and not refunded before". Then the contract, a golden bundle and the seam log.
# Uses: retrieve_case.py, tools_read.py, stages_retrieve.py, tests/s5_world.py, scripts/shop_db.py.
import json

import pytest

from app.pipeline import observe
from tests.s5_world import ask, ids, make_lane, needs_postgres, query_for, text_of, visitor_says
from tests.test_s1_refund_chat import FIRST

pytestmark = needs_postgres

# Config
CURRENT_POLICIES = {"item_policy_window", "item_policy_auto_limit", "item_policy_late_large"}
LATEST = "order:ORD-1002"


@pytest.fixture
def anna():
    """Given the chat is connected and the shop's database is connected, when Anna asks for a refund."""
    lane = make_lane()
    return lane, visitor_says(lane, FIRST)


# --- BDD: the S5 lines

def test_the_refund_agent_finds_annas_latest_order(anna):
    lane, task = anna
    bundle, decision = ask(lane, query_for(lane, task))
    orders = [item for item in bundle.items if item.item_id.startswith("order:")]
    assert [item.item_id for item in orders] == [LATEST, "order:ORD-1001"]  # newest first, read from the shop's database
    assert text_of(bundle, LATEST) == ("Order ORD-1002: Wireless mouse, LKR 4,000.00, paid 30 September 2026 with payment "
                                       "pay_FB_20260930_0144; status paid; no refund yet.")
    assert orders[0].source.uri == "db://conn_shop_db/orders/ORD-1002" and orders[0].sensitivity == "confidential"
    assert decision.decision == "allow" and "2 orders" in decision.reason


def test_the_refund_agent_checks_the_policy_in_force_today(anna):
    lane, task = anna
    bundle, _ = ask(lane, query_for(lane, task))
    assert CURRENT_POLICIES <= ids(bundle)
    assert not ids(bundle) & {"item_policy_window_v1", "item_policy_window_v2", "item_policy_auto_limit_v2", "item_policy_window_v4"}
    assert "within 30 days" in text_of(bundle, "item_policy_window") and "LKR 50,000" in text_of(bundle, "item_policy_auto_limit")


def test_the_bundle_holds_what_the_check_needs_inside_30_days_under_the_limit_never_refunded(anna):
    lane, task = anna
    bundle, _ = ask(lane, query_for(lane, task))
    latest = text_of(bundle, LATEST)
    assert "30 September 2026" in latest and "LKR 4,000.00" in latest and "no refund yet" in latest  # 10 days ago, under LKR 50,000
    assert "refunded LKR 18,500.00 so far" in text_of(bundle, "order:ORD-1001")  # the earlier order was refunded: not this one


def test_the_chat_so_far_is_in_the_bundle(anna):
    lane, task = anna
    bundle, _ = ask(lane, query_for(lane, task))
    assert text_of(bundle, "msg:sig_0001") == f"Customer wrote: {FIRST['text']}"


# --- Contract: what S6 reads, the access decision, and the seam log

def test_the_bundle_matches_the_golden_master(anna):
    lane, task = anna
    bundle, decision = ask(lane, query_for(lane, task))
    assert sorted(ids(bundle)) == sorted(CURRENT_POLICIES | {LATEST, "order:ORD-1001", "msg:sig_0001"})  # reviewed by hand, then frozen
    assert (bundle.denied_count, decision.rule_id, decision.action, decision.principal_id) == (1, "sensitivity_by_tier", "kb.read", "agent_refund_worker")
    assert decision.reason == "3 shown, 1 withheld, searched entity; case: 2 orders, 3 shown, 0 withheld"  # the 1 withheld: the restricted fraud note


def test_no_name_or_email_leaves_the_shop(anna):
    lane, task = anna
    bundle, _ = ask(lane, query_for(lane, task))
    texts = json.dumps([item.model_dump(mode="json") for item in bundle.items])
    assert "anna@example.lk" not in texts and "Perera" not in texts and "cus_anna" not in texts


def test_the_seam_log_records_ids_only(anna, tmp_path, monkeypatch):
    lane, task = anna
    monkeypatch.setattr(observe, "SEAM_LOG_DIR", str(tmp_path))
    bundle, _ = ask(lane, query_for(lane, task))
    line = json.loads((tmp_path / "S5.jsonl").read_text().splitlines()[-1])
    assert line["out"]["items"] == [item.item_id for item in bundle.items] and line["in"]["customer"] is True
    logged = json.dumps(line)
    assert "anna@example.lk" not in logged and "Perera" not in logged and "Wireless" not in logged  # ids, never her details or her orders


def test_the_query_s4_sends_names_the_customer_and_the_chat(anna):
    lane, task = anna
    query = query_for(lane, task)
    assert query.customer_ref.startswith("pii_tok_") and query.conversation_id == "conn_web_chat:chat_sess_anna"
