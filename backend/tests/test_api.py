# test_api.py: the Finebase HQ console API (step 9a): served screens in the console's shapes, decide with S8's rules,
# errors, empty fallbacks for screens not built yet, and the live stream. Memory pipeline, recorded Claude.
# Uses: app/api/routes.py, app/api/hq.py (load_hq), capture_api.py, orchestrate.py, tests/golden.py.
import json

import pytest
from fastapi.testclient import TestClient

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import capture_api, fakes, orchestrate
from tests.golden import NOW, RAW, recorded_answers

# Config
SEED, HQ = load_hq()
TENANT = SEED["tenant_id"]
FOUNDER, STEWARD = "h-pamuditha", "h-udayanga"


# --- Helpers

@pytest.fixture
def hq():
    """The HQ API over a memory pipeline that has handled the s2 (auto) and s3 (needs approval) emails."""
    gateway, paid = fakes.make_fake_gateway()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], gateway, NOW)
    client = TestClient(create_api_app(lane, HQ))
    for key in ("s2_refund_monthly_in_policy", "s3_refund_annual_late_large"):
        body = RAW[key]["raw_body"].encode()
        headers = {"content-type": "message/rfc822", "x-external-id": RAW[key]["external_id"], "x-signature": capture_api.sign(SEED["connectors"]["conn_gmail_support"]["secret"], body)}
        assert client.post("/capture/conn_gmail_support", content=body, headers=headers).status_code == 202
        lane.bus.drain()
    return client, lane, paid


def get(client, resource: str, persona: str = FOUNDER):
    return client.get(f"/api/t/{TENANT}/{resource}", headers={"x-persona": persona})


def decide(client, approval_id: str, persona: str, decision: str = "approve"):
    return client.post(f"/api/t/{TENANT}/ops/decide", json={"approvalId": approval_id, "decision": decision, "comment": ""}, headers={"x-persona": persona})


# --- Shell

def test_tenant_people_and_cluster(hq):
    client, _, _ = hq
    assert client.get("/api/tenants").json() == [{"id": "finebase-hq", "name": "Finebase HQ", "isScaleDemo": False}]
    tenant = get(client, "tenant").json()
    assert (tenant["name"], tenant["criticalityThresholds"]["refundAutoLimitMinor"]) == ("Finebase HQ", 5000000)
    people = {h["name"]: (h["tier"], h["maxApprovalCriticality"]) for h in get(client, "humans").json()}
    assert people == {"Pamuditha Senanayake": ("L1", 4), "Udayanga Weerakoon": ("L2", 2), "Imashi Dissanayake": ("L2", 2)}
    assert get(client, "clusters").json()[0]["id"] == "customer_care"


# --- Lane A screens

def test_runs_escalations_and_detail(hq):
    client, _, _ = hq
    runs = get(client, "runs").json()
    assert sorted(run["status"] for run in runs) == ["awaiting_approval", "succeeded"]
    assert {run["subject"] for run in runs} == {"Issue refund LKR 12,000", "Issue refund LKR 85,000"}
    waiting = get(client, "escalations").json()
    assert len(waiting) == 1 and waiting[0]["escalation"]["assignee"] == FOUNDER and waiting[0]["escalation"]["risk"] == "high"
    detail = get(client, f"runs/{waiting[0]['id']}").json()
    judgment = next(step for step in detail["steps"] if step["kind"] == "judgment")
    assert {fact["id"] for fact in judgment["facts"]} >= {"item_payment_s3"}


def test_approval_follows_s8_rules(hq):
    client, lane, paid = hq
    approval = get(client, "approvals").json()[0]
    assert (approval["status"], approval["dri"], approval["criticality"]) == ("pending", FOUNDER, 3)
    refused = decide(client, approval["id"], STEWARD)
    assert (refused.status_code, refused.json()["error"]) == (409, "not_an_approver")
    assert decide(client, approval["id"], FOUNDER).status_code == 200
    lane.bus.drain()
    assert get(client, f"approvals/{approval['id']}").json()["status"] == "approved" and len(paid) == 2
    assert decide(client, approval["id"], FOUNDER).json()["error"] == "approval_closed"


def test_access_log_and_audit(hq):
    client, _, _ = hq
    decisions = get(client, "access-decisions?principal=agent_refund_worker").json()
    assert {d["action"] for d in decisions} == {"kb.read", "refund.propose"} and all(d["runId"] for d in decisions)
    audit = get(client, "audit").json()
    correlation = audit[0]["correlationId"]
    assert audit and all(event["correlationId"] == correlation for event in get(client, f"audit?correlation={correlation}").json())


# --- Errors and screens not built yet

@pytest.mark.parametrize("resource, persona, status, body", [
    ("runs", "someone_else", 401, {"error": "unknown_persona"}),
    ("skills", FOUNDER, 200, []),
    ("overview", FOUNDER, 501, {"error": "not_connected_yet"}),
    ("digest", FOUNDER, 200, None),
    ("runs/run_missing", FOUNDER, 404, {"error": "not_found"}),
])
def test_errors_and_fallbacks(hq, resource, persona, status, body):
    client, _, _ = hq
    response = get(client, resource, persona)
    assert (response.status_code, response.json()) == (status, body)


def test_unknown_tenant_and_ops_not_built(hq):
    client, _, _ = hq
    assert client.get("/api/t/demo-fbl/runs", headers={"x-persona": FOUNDER}).status_code == 404
    assert client.post(f"/api/t/{TENANT}/ops/takeover", json={}, headers={"x-persona": FOUNDER}).status_code == 501
    assert client.post(f"/api/t/{TENANT}/ask", json={"question": "hi"}, headers={"x-persona": FOUNDER}).status_code == 501


# --- Live stream

def test_stream_sends_live_events_the_console_reads(hq):
    client, _, _ = hq
    text = client.get(f"/api/t/{TENANT}/stream?limit=1").text.removeprefix("retry: 2000\n\n")  # the reconnect hint comes first
    assert text.startswith("data: ") and not text.startswith("event:")  # unnamed, so the console's onmessage sees it
    event = json.loads(text.removeprefix("data: ").strip())
    assert event["tenantId"] == TENANT and "runs" in event["resources"] and event["summary"]
