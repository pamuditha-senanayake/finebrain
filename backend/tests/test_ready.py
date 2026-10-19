# test_ready.py: step 16 slice 1, obligations. Each sample obligation's next instance falls due on its day (or when a verified
# contract term ends), and its readiness is worked out from verified facts about that period; the console's lists and counts
# follow. Uses: readiness_model.py, readiness_facts.py, api/ready_views.py, tests/golden.py and test_documents.py (HQ seed).
from datetime import datetime, timezone

from app.api.ready_views import obligations_view
from app.pipeline import entity_match, fakes, orchestrate
from app.pipeline.readiness_model import month_before, on_day
from tests.golden import NOW, SEED as GOLDEN_SEED
from tests.test_documents import FOUNDER, TENANT, build

# Config
LANKA_PRINT = ["contract", "supplier agreement lanka print and finebase"]


# --- Helpers

def put_fact(lane, fact_id: str, predicate: str, value: str, valid_from: str, valid_to: str | None = None, subject=None) -> None:
    """A verified fact on main, as step 14 leaves it."""
    ref = entity_match.entity_id_of(*subject) if subject else "ent_organization_x"
    lane.graph.put("fact", fact_id, 1, "cmt_test", {"item_id": fact_id, "kind": "fact", "text": f"{predicate} {value}", "predicate": predicate,
                   "subject": {"entity_type": "contract", "entity_ref": ref}, "value": {"type": "text", "raw": value, "normalized": value},
                   "valid_from": valid_from, "valid_to": valid_to, "status": "verified", "recorded_at": NOW.isoformat(), "sensitivity": "internal"})


def obligations(client) -> dict[str, dict]:
    return {ob["id"].split(":")[0]: ob for ob in client.get(f"/api/t/{TENANT}/obligations", headers={"x-persona": FOUNDER}).json()}


# --- When things fall due

def test_monthly_obligations_fall_due_on_their_day_for_the_month_before():
    client, _ = build()  # the test clock is 10 October 2026
    shown = obligations(client)
    assert shown["ob_apit"]["id"] == "ob_apit:2026-09" and shown["ob_apit"]["dueAt"].startswith("2026-10-15")
    assert shown["ob_vat"]["title"] == "VAT return · September 2026" and shown["ob_vat"]["prepareBy"].startswith("2026-10-13")
    assert shown["ob_annual_return"]["dueAt"].startswith("2027-06-30") and all(ob["isSample"] for ob in shown.values())


def test_a_due_day_past_the_months_end_is_its_last_day():
    assert on_day(2027, 2, 30) == datetime(2027, 2, 28, tzinfo=timezone.utc) and month_before(2027, 1) == "2026-12"


def test_a_renewal_waits_until_a_verified_fact_gives_the_term():
    client, lane = build()
    assert "ob_lanka_print_renewal" not in obligations(client)
    put_fact(lane, "fact_term", "term", "2026-10-01 to 2027-09-30", "2026-10-01T00:00:00+00:00", "2027-09-30T00:00:00+00:00", LANKA_PRINT)
    renewal = obligations(client)["ob_lanka_print_renewal"]
    assert renewal["dueAt"].startswith("2027-09-30") and renewal["prepareBy"].startswith("2027-08-01")


# --- How ready they are

def test_readiness_comes_from_verified_facts_about_that_month():
    client, lane = build()
    assert (obligations(client)["ob_vat"]["readiness"], obligations(client)["ob_vat"]["status"]) == (0, "red")
    put_fact(lane, "fact_in", "vat_input_invoices", "LKR 380000", "2026-09-01T00:00:00+00:00")
    put_fact(lane, "fact_august", "vat_sales_invoices", "LKR 900000", "2026-08-01T00:00:00+00:00")  # the wrong month
    vat = obligations(client)["ob_vat"]
    assert vat["readiness"] == 50 and {i["key"]: i["satisfiedBy"] for i in vat["requiredEvidence"]} == {"input_invoices": "fact_in", "sales_invoices": None}
    put_fact(lane, "fact_out", "vat_sales_invoices", "LKR 1200000 for 2026-09", "2026-10-02T00:00:00+00:00")  # names the month in its value
    assert (obligations(client)["ob_vat"]["readiness"], obligations(client)["ob_vat"]["status"]) == (100, "green")


def test_a_fact_that_ended_proves_nothing():
    client, lane = build()
    put_fact(lane, "fact_old", "apit_deducted", "LKR 50000", "2026-09-01T00:00:00+00:00", "2026-10-01T00:00:00+00:00")
    assert obligations(client)["ob_apit"]["readiness"] == 0


def test_far_off_and_half_ready_is_amber():
    client, lane = build()
    put_fact(lane, "fact_fs", "audited_financial_statements", "FY 2026", "2026-04-01T00:00:00+00:00")  # due June 2027, for 2026
    put_fact(lane, "fact_sh", "shareholders", "2026 register", "2026-03-31T00:00:00+00:00")
    assert obligations(client)["ob_annual_return"]["status"] == "green"
    lane.graph.purge("fact", "fact_sh")
    assert obligations(client)["ob_annual_return"]["status"] == "amber"


# --- Rules, risks and counts

def test_rules_risks_and_the_overview_counts_are_served():
    client, _ = build()
    rules = client.get(f"/api/t/{TENANT}/readiness-rules", headers={"x-persona": FOUNDER}).json()
    risks = client.get(f"/api/t/{TENANT}/risks", headers={"x-persona": FOUNDER}).json()
    assert {"id", "target", "requires", "checkEvery", "escalationDays", "lastRunAt"} == set(rules[0]) and len(risks) == 2
    entity = client.get(f"/api/t/{TENANT}/overview", headers={"x-persona": FOUNDER}).json()["entity"]
    assert entity == {"red": sum(ob["status"] == "red" for ob in obligations(client).values()), "amber": 0, "risks": 2, "evidenceOpen": 0}


def test_a_tenant_without_obligations_shows_none():
    lane = orchestrate.build_lane(GOLDEN_SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    assert obligations_view(lane) == []
