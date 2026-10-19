# test_grants.py: step 16 slice 5, data source grants. A request a source could supply asks for read access; that is C4, so two
# different L1 leaders approve (never the one who asked), a cooling period follows, then the grant is active until revoked. Finebase
# HQ has one L1, so these tests add a test-only second leader. Uses: api/grants.py, grant_views.py, routes.py, tests/test_ready_gaps.py.
from datetime import timedelta

import pytest

from app.api import grants
from tests.test_documents import FOUNDER, TENANT, build
from tests.test_ready_gaps import STEWARD, get

# Config
SECOND = "h-test-leader"
VAT = "er_ob_vat_2026_09_input_invoices"  # its item could come from the finance inbox (sample)
EPF = "er_ob_epf_2026_09_payroll_summary"  # no source is named for it


# --- Helpers

@pytest.fixture
def hq(monkeypatch):
    """Finebase HQ with a test-only second L1 leader, and its requests opened."""
    client, lane = build()
    monkeypatch.setitem(lane.seed["people"], SECOND, {"tier": "L1", "roles": ["leader"], "delegate": None, "name": "Test Leader"})
    get(client, "gaps")
    return client, lane


def post(client, op: str, body: dict, persona: str):
    return client.post(f"/api/t/{TENANT}/ops/{op}", json=body, headers={"x-persona": persona})


def decide(client, lane, approval_id: str, persona: str, decision: str = "approve"):
    answer = post(client, "decide", {"approvalId": approval_id, "decision": decision}, persona)
    lane.bus.drain()
    return answer


def asked(client, lane, persona: str = STEWARD) -> dict:
    return post(client, "requestGrant", {"requestId": VAT}, persona).json()


def request_status(client, request_id: str = VAT) -> str:
    return next(r for r in get(client, "evidence-requests") if r["id"] == request_id)["status"]


# --- Asking

def test_asking_opens_a_c4_approval_and_pauses_the_request(hq):
    client, lane = hq
    answer = asked(client, lane)
    approval = next(a for a in get(client, "approvals") if a["id"] == answer["approvalId"])
    assert (approval["subject"]["kind"], approval["criticality"], approval["status"], approval["drafter"]["id"]) == ("grant", 4, "pending", STEWARD)
    assert request_status(client) == "awaiting_grant_approval" and get(client, "grants")[0]["status"] == "pending"
    assert {n["to"] for n in lane.records.list_kind("notification") if n["title"].startswith("C4: grant")} == {FOUNDER, SECOND}


def test_only_a_request_with_a_source_can_ask_and_only_once(hq):
    client, lane = hq
    assert post(client, "requestGrant", {"requestId": EPF}, STEWARD).status_code == 409
    assert post(client, "requestGrant", {"requestId": "er_nothing"}, STEWARD).status_code == 404
    asked(client, lane)
    assert post(client, "requestGrant", {"requestId": VAT}, STEWARD).status_code == 409


# --- Deciding

def test_two_leaders_approve_then_after_cooling_the_grant_is_active(hq):
    client, lane = hq
    approval_id = asked(client, lane)["approvalId"]
    assert decide(client, lane, approval_id, FOUNDER).json() == {"ok": True} and get(client, "grants")[0]["status"] == "pending"
    decide(client, lane, approval_id, SECOND)
    grants.sweep(lane)
    assert get(client, "grants")[0]["status"] == "pending"  # approved, still cooling
    lane.now += timedelta(hours=25)
    grants.sweep(lane)
    assert get(client, "grants")[0]["status"] == "active" and request_status(client) == "open"
    assert next(g for g in get(client, "gaps") if g["id"] == "gap_ob_vat_2026_09_input_invoices")["action"] == "request_dri"  # the source is granted now


def test_the_one_who_asked_never_approves_and_a_steward_cannot(hq):
    client, lane = hq
    approval_id = asked(client, lane, FOUNDER)["approvalId"]
    assert decide(client, lane, approval_id, FOUNDER).status_code == 409 and decide(client, lane, approval_id, STEWARD).status_code == 409
    assert get(client, "grants")[0]["status"] == "pending"  # on Finebase HQ alone it waits here: there is no second L1


def test_a_rejection_gives_the_request_back_to_the_dri(hq):
    client, lane = hq
    approval_id = asked(client, lane)["approvalId"]
    decide(client, lane, approval_id, FOUNDER, "reject")
    assert get(client, "grants")[0]["status"] == "revoked" and request_status(client) == "open"  # the console shows a rejected grant as revoked


# --- Revoking

def test_an_active_grant_can_be_revoked_by_a_steward(hq):
    client, lane = hq
    approval_id = asked(client, lane)["approvalId"]
    decide(client, lane, approval_id, FOUNDER)
    decide(client, lane, approval_id, SECOND)
    lane.now += timedelta(hours=25)
    grants.sweep(lane)
    grant_id = get(client, "grants")[0]["id"]
    assert post(client, "revokeGrant", {"grantId": grant_id}, STEWARD).json() == {"ok": True}
    assert get(client, "grants")[0]["status"] == "revoked" and post(client, "revokeGrant", {"grantId": grant_id}, STEWARD).status_code == 409
    assert [e["topic"] for e in lane.audit.in_order() if e["topic"].startswith("grant.")] == ["grant.activated", "grant.revoked"]
