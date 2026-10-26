# test_s6_rules.py: rules S6 keeps whatever the model proposes. Many random customers and random refund attempts (any
# shop payment, any amount, any citations, asked first or not): every refund S6 lets through is this customer's own
# order, cited, no more than is left on it, and in a chat only after the customer confirmed. Real shop database.
# Uses: run_steps.py, reason_checks.py, tests/s5_world.py, tests/s6_world.py, scripts/shop_db.py.
import random

import pytest

from scripts import shop_db
from tests.s5_world import make_lane, needs_postgres
from tests.s6_world import ask, refund, scripted, visit_1, visit_2

pytestmark = needs_postgres

# Config
SHOP = shop_db.WORLD
VISITORS = [("anna@example.lk", "cus_anna"), ("ben@example.lk", "cus_ben"), ("chen@example.lk", "cus_chen"), ("dee@example.lk", "cus_dee"), (None, None)]
LEFT = {o["payment_ref"]: o["total_minor"] - sum(r["amount_minor"] for r in SHOP["refunds"] if r["order_id"] == o["id"]) for o in SHOP["orders"]}


def attempt(picker: random.Random, customer: str | None) -> dict:
    """A refund a model might propose: often the visitor's own order, sometimes anyone's; any amount; citing it or not."""
    own = [o for o in SHOP["orders"] if o["customer_id"] == customer]
    order = picker.choice(own if own and picker.random() < 0.7 else SHOP["orders"])
    citations = picker.choice([[f"order:{order['id']}", "item_policy_window"], [f"order:{order['id']}"], ["item_policy_window"]])
    amount = picker.choice([order["total_minor"], order["total_minor"], 100, order["total_minor"] + 100])
    return refund(payment_ref=order["payment_ref"], amount={"amount_minor": amount, "currency": "LKR"}, citations=citations)


@pytest.mark.parametrize("seed", range(60))
def test_every_refund_s6_lets_through_keeps_the_rules(seed):
    picker = random.Random(seed)
    email, customer = picker.choice(VISITORS)
    asked_first = picker.random() < 0.5
    lane = make_lane()
    tries = [attempt(picker, customer) for _ in range(3)]
    question = ask("Which order is it?", citations=["item_policy_window"])  # true for any visitor
    lane.model, _ = scripted(*([question] if asked_first else []), *tries, *tries)
    who = {"email": email, "session": f"sess_{seed}", "name": "Visitor"}
    _, _, action = visit_1(lane, {"id": f"a{seed}", "text": "I want a refund for my last order"}, **who)
    if asked_first:
        _, _, action = visit_2(lane, {"id": f"b{seed}", "text": "yes, that one"}, **who)
    if action.action_type != "issue_refund":
        return
    ref = action.arguments["payment_ref"]
    owner = next(o for o in SHOP["orders"] if o["payment_ref"] == ref)["customer_id"]
    assert owner == customer and asked_first  # only their own order, and only after they confirmed
    assert action.money.amount_minor <= LEFT[ref] and f"order:{next(o['id'] for o in SHOP['orders'] if o['payment_ref'] == ref)}" in action.citations
