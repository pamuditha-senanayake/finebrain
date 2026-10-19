# test_ready_gaps.py: step 16 slice 2, S15's check. Every required item no verified fact proves is a gap with an owner; the first
# check opens one request per gap, tells the DRI, audits it and publishes K15; checking again opens nothing new; a fact that proves
# the item fulfils its request. Uses: stages_ready.py, api/ready_views.py, ready_routes.py, tests/test_ready.py (helpers).
from datetime import timedelta

from app.pipeline import stages_ready
from tests.test_documents import FOUNDER, TENANT, build
from tests.test_ready import put_fact

# Config
STEWARD = "h-udayanga"


# --- Helpers

def get(client, resource: str, persona: str = FOUNDER):
    return client.get(f"/api/t/{TENANT}/{resource}", headers={"x-persona": persona}).json()


def check_now(client, persona: str = FOUNDER):
    return client.post(f"/api/t/{TENANT}/ops/runReadinessScheduler", headers={"x-persona": persona})


# --- The step's done check

def test_a_missing_filing_shows_up_as_a_gap_with_an_owner():
    client, lane = build()
    gaps = {g["id"]: g for g in get(client, "gaps")}
    vat = gaps["gap_ob_vat_2026_09_input_invoices"]
    assert (vat["missing"], vat["dri"], vat["action"], vat["target"]["label"]) == ("Input VAT invoices", FOUNDER, "request_dri", "VAT return · September 2026")
    assert vat["requestId"] == "er_ob_vat_2026_09_input_invoices"


# --- What the first check does

def test_the_first_check_opens_one_request_per_gap_and_says_so():
    client, lane = build()
    gaps = get(client, "gaps")
    requests = get(client, "evidence-requests")
    assert len(requests) == len(gaps) and {r["status"] for r in requests} == {"open"} and {r["requestedFrom"] for r in requests} == {FOUNDER}
    published = [e.payload for e in lane.bus.topics["evidence.gaps"]]
    assert len(published) == len(gaps) and all(p["is_sample"] and p["action"] == "request_dri" for p in published)
    assert sum(n["title"].startswith("Evidence needed") for n in lane.records.list_kind("notification")) == len(gaps)
    assert sum(entry["topic"] == "evidence.requested" for entry in lane.audit.in_order()) == len(gaps)


def test_checking_again_opens_nothing_new():
    client, lane = build()
    get(client, "gaps")
    answer = check_now(client).json()
    assert answer["requestsCreated"] == 0 and answer["gaps"] == len(get(client, "gaps"))
    assert len(lane.bus.topics["evidence.gaps"]) == answer["gaps"]


def test_a_request_close_to_its_day_has_escalated():
    client, _ = build()  # VAT's prepare-by day is 13 October, under three full days after the test clock: past all four steps
    vat = next(r for r in get(client, "evidence-requests") if r["id"] == "er_ob_vat_2026_09_input_invoices")
    assert vat["escalationLevel"] == 4 and vat["obligationId"] == "ob_vat:2026-09"


# --- When the proof arrives

def test_a_verified_fact_fulfils_the_request_and_closes_the_gap():
    client, lane = build()
    get(client, "gaps")
    put_fact(lane, "fact_in", "vat_input_invoices", "LKR 380000", "2026-09-01T00:00:00+00:00")
    check_now(client)
    request = next(r for r in get(client, "evidence-requests") if r["id"] == "er_ob_vat_2026_09_input_invoices")
    assert request["status"] == "fulfilled" and request["fulfilledBy"] == {"kind": "upload", "ref": "fact_in"}
    assert "gap_ob_vat_2026_09_input_invoices" not in {g["id"] for g in get(client, "gaps")}


# --- Who may check, when it runs, and the counts

def test_a_steward_may_check_and_a_stranger_may_not():
    client, _ = build()
    assert check_now(client, STEWARD).status_code == 200 and check_now(client, "h-stranger").status_code == 401


def test_the_screens_run_the_check_once_an_hour():
    client, lane = build()
    get(client, "gaps")
    first = lane.records.load(stages_ready.CHECK_KIND, "latest")["at"]
    get(client, "evidence-requests")
    assert lane.records.load(stages_ready.CHECK_KIND, "latest")["at"] == first
    lane.now += timedelta(hours=2)
    get(client, "gaps")
    assert lane.records.load(stages_ready.CHECK_KIND, "latest")["at"] != first


def test_the_overview_counts_open_requests():
    client, _ = build()
    entity = get(client, "overview")["entity"]
    assert entity["evidenceOpen"] == sum(r["status"] == "open" for r in get(client, "evidence-requests")) > 0
