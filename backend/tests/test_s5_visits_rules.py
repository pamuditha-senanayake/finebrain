# test_s5_visits_rules.py: S5 reached more than once by one chat, and rules that hold for any customer, time and reader.
# Visit 1: Anna asks for a refund. Visit 2: "yes, that one" joins her run, and S5 asked again sees the whole chat and
# the shop as it is now. Then many random cases over the real shop database.
# Uses: retrieve_case.py, stages_orchestrate.py, tests/s5_world.py, samples/shop_world.json, scripts/shop_db.py.
import json
import random
from datetime import datetime

import psycopg
import pytest

from app.pipeline import stages_orchestrate
from scripts import shop_db
from tests.s5_world import ask, ids, make_lane, needs_postgres, query_for, text_of, visitor_says
from tests.test_s1_refund_chat import FIRST, SECOND

pytestmark = needs_postgres

# Config
SHOP = shop_db.WORLD
CUSTOMERS = {"anna@example.lk": "cus_anna", "ben@example.lk": "cus_ben", "chen@example.lk": "cus_chen", "dee@example.lk": "cus_dee", None: None}
DAYS = ["2024-06-01", "2025-06-01", "2026-07-05", "2026-08-01", "2026-10-10", "2026-11-15"]
AGENTS = ["agent_refund_worker", "agent_risk_reviewer", "agent_greeter"]
PEOPLE = [None, "support_operator_1", "steward_1", "head_of_cs"]
WINDOW_IDS = {"item_policy_window_v1", "item_policy_window_v2", "item_policy_window", "item_policy_window_v4"}


def start_latest_task(lane) -> None:
    """S4 handles the newest task, so a later message on the chat joins its run."""
    stages_orchestrate.begin_run(lane, lane.bus.topics["tasks.created"][-1])


# --- Visit 2 asks S5 again

def test_visit_2_sees_the_whole_chat_and_the_shop_as_it_is_now():
    lane = make_lane()
    first = visitor_says(lane, FIRST)
    start_latest_task(lane)
    visit_1, _ = ask(lane, query_for(lane, first))
    with psycopg.connect(shop_db.owner_url(), autocommit=True) as shop:  # between the visits, the shop files a refund on the mouse
        shop.execute("INSERT INTO shop.refunds VALUES ('RF-0003', 'ORD-1002', 400000, 'approved', '2026-10-10T09:58:00+05:30')")
    follow_up = visitor_says(lane, SECOND)  # no rule matches "yes, that one"; S3 hands it on for the open run
    assert "continues_open_run" in follow_up["flags"]
    visit_2, _ = ask(lane, query_for(lane, follow_up))
    assert [i for i in [item.item_id for item in visit_1.items] if i.startswith("msg:")] == ["msg:sig_0001"]
    assert [i for i in [item.item_id for item in visit_2.items] if i.startswith("msg:")] == ["msg:sig_0001", "msg:sig_0002"]
    assert "no refund yet" in text_of(visit_1, "order:ORD-1002") and "refunded LKR 4,000.00 so far" in text_of(visit_2, "order:ORD-1002")


def test_another_chat_at_the_same_time_never_reaches_annas_bundle():
    lane = make_lane()
    anna = visitor_says(lane, FIRST)
    visitor_says(lane, {"id": "msg_ben_1", "text": "I want a refund for my desk lamp"}, email="ben@example.lk", session="chat_sess_ben", name="Ben")
    bundle, _ = ask(lane, query_for(lane, anna))
    assert {i for i in ids(bundle) if i.startswith(("msg:", "order:"))} == {"msg:sig_0001", "order:ORD-1001", "order:ORD-1002"}


# --- Rules that always hold

def payment_refs_of(customer_id: str | None) -> set[str]:
    return {o["payment_ref"] for o in SHOP["orders"] if o["customer_id"] == customer_id}


@pytest.mark.parametrize("seed", range(40))
def test_rules_hold_for_any_customer_time_and_reader(seed):
    picker = random.Random(seed)
    email = picker.choice(list(CUSTOMERS))
    day, agent, person = picker.choice(DAYS), picker.choice(AGENTS), picker.choice(PEOPLE)
    lane = make_lane()
    task = visitor_says(lane, {"id": f"m{seed}", "text": "I want a refund for my last order"}, email=email, session=f"s{seed}", name="Visitor")
    as_of = datetime.fromisoformat(f"{day}T12:00:00+05:30")
    bundle, decision = ask(lane, query_for(lane, task, agent_id=agent, on_behalf_of=person, as_of_valid=as_of))
    texts = json.dumps([item.model_dump(mode="json") for item in bundle.items])

    # A reader without kb.read gets nothing; everyone else gets only what was true then, and only this customer's orders
    if agent == "agent_greeter":
        assert bundle.items == [] and decision.decision == "deny"
        return
    assert all(item.valid_from is None or item.valid_from <= as_of for item in bundle.items)
    assert all(item.valid_to is None or item.valid_to > as_of for item in bundle.items if not item.item_id.startswith("order:"))
    shown_refs = {o["payment_ref"] for o in SHOP["orders"] if o["payment_ref"] in texts}
    assert shown_refs <= payment_refs_of(CUSTOMERS[email])
    assert len(ids(bundle) & WINDOW_IDS) <= 1  # never two refund windows at once
    # Restricted notes only for L2 and up, on both sides; no name or email ever leaves the shop
    l3_involved = agent == "agent_refund_worker" or person == "support_operator_1"
    assert not (l3_involved and "item_fraud_watch" in ids(bundle))
    assert not any(customer["email"] in texts or customer["name"] in texts for customer in SHOP["customers"])
