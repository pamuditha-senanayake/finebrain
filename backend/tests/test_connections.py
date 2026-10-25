# test_connections.py: line 1 of the refund BDD. The guide drafts a connection, the brief follows its needs, the other
# side's whole answer is pasted back (settings and keys picked out), the test reads only, an L1 goes live, and customer
# messages come in through S1 and S2 with a thread. A bad key or bad settings fail plainly.
import hmac
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.api import connect_brief
from app.pipeline import conn_call, conn_inbound, fakes, orchestrate
from tests.golden import NOW

# Config
SEED, HQ = load_hq()
TENANT = SEED["tenant_id"]
FOUNDER, STEWARD = "h-pamuditha", "h-udayanga"
MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "samples" / "findbase_portal_manifest.json").read_text())
KEY = "test-only-portal-key"
MESSAGES = [
    {"id": "m-1", "conversation_id": "c-1", "seq": 1, "sender": "customer", "body": "I want a refund for my last order", "created_at": "2026-10-20T09:00:00Z", "conversations": {"customer_id": "cust-amara"}},
    {"id": "m-2", "conversation_id": "c-1", "seq": 2, "sender": "agent", "body": "Hello", "created_at": "2026-10-20T09:00:01Z", "conversations": {"customer_id": "cust-amara"}},
]


def fake_portal(request: httpx.Request) -> httpx.Response:
    """Answers like the portal's hub API: bearer key, cursor, conversation context."""
    if request.headers.get("authorization") != f"Bearer {KEY}":
        return httpx.Response(401, json={"error": "Unauthorized"})
    since = int(request.url.params.get("since", 0))
    if request.url.path == "/api/hub/messages" and request.method == "GET":
        return httpx.Response(200, json={"messages": [m for m in MESSAGES if m["seq"] > since], "nextSince": max([since] + [m["seq"] for m in MESSAGES])})
    if request.url.path.startswith("/api/hub/conversations/"):
        return httpx.Response(200, json={"conversation": {"id": "c-1"}, "customer": {"id": "cust-amara"}, "orders": []})
    if request.url.path.startswith("/api/hub/customers/"):
        return httpx.Response(200, json={"customer": {"id": "cust-amara"}})
    if request.method == "PATCH":
        return httpx.Response(200, json={"ok": True})
    return httpx.Response(404, json={"error": "not found"})


DRAFT = {"name": "Shop website", "system": "Shop website with a support chat", "goal": "Answer customers and handle refunds in the chat",
         "purpose": "website_chat", "feed": "New customer messages", "needs": [
             {"name": "chat_inbound", "text": "duplicate of the feed"}, {"name": "reply", "text": "Reply in the chat", "writes": True},
             {"name": "conversation", "text": "Read one conversation"}, {"name": "Bad Name", "text": "dropped"}]}


def answer_text(manifest: dict, key: str = KEY) -> str:
    """What the other side's coding agent answers: some words, then the block."""
    block = json.dumps({"manifest": manifest, "api_key": key, "webhook_secret": "<only if you push, else leave out>"})
    return f"Done. I exposed the hub endpoints.\n\n```brain-connection\n{block}\n```\nPaste this into the brain."


@pytest.fixture
def desk(monkeypatch):
    monkeypatch.setattr(conn_call, "http", httpx.Client(transport=httpx.MockTransport(fake_portal)))
    chatter = lambda system, messages, tools: fakes.tool_response("draft_connection", DRAFT)  # noqa: E731
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    return TestClient(create_api_app(lane, HQ, chatter=chatter)), lane


def post(client, path: str, body: dict, persona: str = FOUNDER):
    return client.post(f"/api/t/{TENANT}/{path}", json=body, headers={"x-persona": persona})


def drafted(client) -> dict:
    turns = [{"role": "user", "text": "Connect our shop website chat so the brain answers customers"}]
    return post(client, "connections/guide", {"turns": turns}).json()["connection"]


# --- The desk

def test_guide_drafts_and_the_brief_follows_the_needs(desk):
    client, _ = desk
    connection = drafted(client)
    assert connection["status"] == "waiting" and [n["name"] for n in connection["needs"]] == ["inbound", "reply", "conversation"]
    brief = client.get(f"/api/t/{TENANT}/connections/{connection['id']}/brief", headers={"x-persona": FOUNDER}).json()["brief"]
    for words in (HQ["tenant"]["name"], "Shop website with a support chat", "Answer customers", "`reply`", "```brain-connection", "Deployment Protection", "cursor"):
        assert words in brief


def test_answer_test_live_then_messages_come_in_with_a_thread(desk):
    client, lane = desk
    connection_id = drafted(client)["id"]

    # Step 1: paste their whole answer; settings and key are picked out, the key never shown
    delivered = post(client, f"connections/{connection_id}/deliver", {"answer": answer_text(MANIFEST)}).json()
    assert delivered["status"] == "delivered" and delivered["secretsSet"] == ["api_key"] and KEY not in json.dumps(delivered)

    # Step 2: test reads only; writes are listed, not called
    tested = post(client, f"connections/{connection_id}/test", {}).json()
    assert tested["status"] == "tested", tested["tests"]
    assert {line["item"]: line["ok"] for line in tested["tests"]}["Reply"] is None

    # Step 3: only an L1 switches it live
    assert post(client, f"connections/{connection_id}/live", {"on": True}, STEWARD).status_code == 403
    assert post(client, f"connections/{connection_id}/live", {"on": True}).json()["status"] == "live"

    # Step 4: one poll takes the customer's message (not the agent's) through S1 and S2
    assert conn_inbound.poll_once(lane, conn_call.load(lane, connection_id)) == 1
    lane.bus.drain()
    signals = list(lane.signals.values())
    assert [s.thread_ref for s in signals] == [f"{connection_id}:c-1"]
    assert signals[0].actor.ref == "cust-amara" and signals[0].channel == "chat"

    # Step 5: the cursor moved, so a second poll takes nothing
    assert conn_inbound.poll_once(lane, conn_call.load(lane, connection_id)) == 0


def test_bad_answer_and_bad_key_fail_plainly(desk):
    client, _ = desk
    connection_id = drafted(client)["id"]
    broken = post(client, f"connections/{connection_id}/deliver", {"answer": "Sorry, I could not find the endpoints."})
    assert broken.status_code == 422 and "No settings block" in broken.json()["error"]["problems"][0]
    post(client, f"connections/{connection_id}/deliver", {"answer": answer_text(MANIFEST, key="wrong")})
    lines = post(client, f"connections/{connection_id}/test", {}).json()["tests"]
    assert lines[-1] == {"item": "Feed in", "ok": False, "detail": "The key was refused (401)"}
    assert post(client, f"connections/{connection_id}/live", {"on": True}).status_code == 409


def test_a_system_without_a_feed_tests_its_reads():
    manifest = {"name": "CRM", "base_url": "https://crm.example.com", "actions": {"customers": {"method": "GET", "path": "/customers"}}}
    found, secrets, problems = connect_brief.read_answer(f"Here you go:\n```json\n{json.dumps(manifest)}\n```\nAPI_KEY=abc123")
    assert found.inbound is None and secrets == {"api_key": "abc123"} and problems == []


def test_signed_push_is_checked(desk):
    client, lane = desk
    connection_id = drafted(client)["id"]
    post(client, f"connections/{connection_id}/deliver", {"answer": answer_text(MANIFEST), "webhook_secret": "test-only-whsec"})
    post(client, f"connections/{connection_id}/test", {})
    post(client, f"connections/{connection_id}/live", {"on": True})
    body = json.dumps({"event": "message.created", "message": MESSAGES[0]}).encode()
    assert client.post(f"/capture/connections/{connection_id}/push", content=body, headers={"X-Findbase-Signature": "sha256=bad"}).status_code == 401
    good = "sha256=" + hmac.new(b"test-only-whsec", body, "sha256").hexdigest()
    assert client.post(f"/capture/connections/{connection_id}/push", content=body, headers={"X-Findbase-Signature": good}).json() == {"taken": 1}

