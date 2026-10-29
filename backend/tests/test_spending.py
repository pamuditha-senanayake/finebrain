# test_spending.py: A4. A receipt added through Lisena's chat becomes a spend; each month is checked against the budget
# from the "Spending" workflow in Studio; repeats are subscriptions; people add, fix and remove spends by hand.
# Uses: app/api/spending.py, intake.py, intake_talk.py, brain_workflows.py, tests/studio_helpers.py.
from app.api import brain_workflows as flows
from tests.studio_helpers import FOUNDER, TENANT, build, change, op
from tests.golden import NOW

RECEIPT = b"""Google Cloud invoice
Billing account: Finebase Labs
Firebase Blaze plan usage
Total due: $249.00
"""
MONTH = NOW.date().isoformat()


def post(client, path: str, **kwargs):
    return client.post(f"/api/t/{TENANT}/{path}", headers={"x-persona": FOUNDER}, **kwargs)


def overview(client) -> dict:
    return client.get(f"/api/t/{TENANT}/spending", headers={"x-persona": FOUNDER}).json()


def add_receipt(client) -> dict:
    draft = post(client, "intake", files={"file": ("blaze_invoice.txt", RECEIPT)}).json()
    for text in [MONTH, "the company", "Pamuditha", "Google Cloud", "cloud and hosting", "every month"]:
        draft = post(client, f"intake/{draft['intakeId']}/say", json={"text": text}).json()
    return draft


def test_the_receipt_says_its_own_kind_and_total():
    client, _ = build()
    draft = post(client, "intake", files={"file": ("blaze_invoice.txt", RECEIPT)}).json()
    assert (draft["fields"]["kind"], draft["fields"]["amount"], draft["fields"]["currency"]) == ("receipt", 249.0, "USD")
    assert "for USD 249.00" in draft["reply"]


def test_a_filed_receipt_is_a_spend_against_the_budget():
    client, lane = build()
    draft = add_receipt(client)
    assert draft["ready"], draft["questions"]
    done = post(client, f"intake/{draft['intakeId']}/say", json={"text": "yes"}).json()
    assert done["spend"]["vendor"] == "Google Cloud" and "I logged USD 249.00 to Google Cloud" in done["reply"]
    assert "83% of the USD 300 budget, close to the budget" in done["reply"]
    month = overview(client)
    assert (month["month"]["spent"], month["month"]["state"]) == (249.0, "close")
    assert month["byCategory"] == [{"category": "cloud", "label": "Cloud and hosting", "spent": 249.0}]
    assert month["subscriptions"][0]["perMonth"] == 249.0 and month["spends"][0]["source"]["title"].startswith("Receipt · Company")
    assert post(client, f"intake/{draft['intakeId']}/say", json={"text": "yes"}).json()["reply"] == "That one is already added."
    assert len(lane.records.list_kind("spend")) == 1


def test_spends_by_hand_are_checked_fixed_and_removed():
    client, _ = build()
    added = post(client, "spending", json={"vendor": "Figma", "amount": "15 dollars", "currency": "USD", "category": "software", "repeats": "monthly"}).json()
    assert added["amount"] == 15.0 and added["paidOn"] == MONTH
    assert post(client, "spending", json={"vendor": "Figma", "amount": "free", "currency": "USD", "category": "software"}).json()["error"] == "bad_amount"
    assert post(client, "spending", json={"vendor": "Figma"}).json()["error"] == "missing:amount,currency,category"
    over = post(client, f"spending/{added['id']}", json={"amount": 400}).json()
    assert over["amount"] == 400.0 and overview(client)["month"]["state"] == "over"
    post(client, f"spending/{added['id']}", json={"remove": True})
    assert overview(client)["spends"] == [] and post(client, f"spending/{added['id']}", json={"amount": 1}).status_code == 404


def test_other_currencies_are_kept_apart_from_the_budget():
    client, _ = build()
    post(client, "spending", json={"vendor": "Dialog", "amount": "LKR 12,500", "currency": "LKR", "category": "office"})
    month = overview(client)["month"]
    assert month["spent"] == 0 and month["otherCurrencies"] == ["LKR"]


def test_the_budget_comes_from_studio():
    client, lane = build()
    edit = change("policy", flows.BUDGET_POLICY, {"fields": {"param.monthlyBudget": 1000}}, workflow=flows.SPENDING)
    assert op(client, "studioApply", {"input": edit, "acknowledgeBreaking": True}).json()["status"] == "applied"
    lane.bus.drain()
    post(client, "spending", json={"vendor": "AWS", "amount": 100, "currency": "USD", "category": "cloud"})
    assert overview(client)["month"]["usedPercent"] == 10.0
