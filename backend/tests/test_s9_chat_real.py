# test_s9_chat_real.py: S9's replies into the real chat: the Finebase Labs portal (its hub API on Vercel), in Amara's own
# conversation. Every reply is read back from the portal. Her chat as one conversation (asked, then answered, each reply in
# her chat), once per key (a retry, two workers on Valkey, an answer lost after the post), and a refused key posting nothing.
# Skips when the portal key or the portal is missing. The key is read from the portal owner's local guide, never the repo.
# Uses: tools_chat.py, stages_act.py, conn_inbound.py, conn_call.py, tests/s7_world.py, samples/findbase_portal_manifest.json.
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest

from app.pipeline import conn_call, conn_inbound, stages_act, tools_chat
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.conn_call import Connection
from app.pipeline.conn_spec import Manifest
from tests.s6_world import scripted
from tests.s7_world import actions, full_lane, runs
from tests.test_act import EXECUTE, REFUND, tooling

# Config
GUIDE = Path(os.environ.get("HUB_CONNECTION_FILE", Path.home() / "Downloads" / "HUB_CONNECTION.local.md"))
MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "samples" / "findbase_portal_manifest.json").read_text())
PORTAL, AMARA_CHAT, AMARA = "conn-portal-chat", "4932e8fb-246a-4523-9073-74fe91bdb5aa", "11111111-1111-4111-8111-111111111111"


def portal_key() -> str | None:
    match = re.search(r"^HUB_API_KEY=(\S+)", GUIDE.read_text(), re.MULTILINE) if GUIDE.exists() else None
    return os.environ.get("FINEBASE_HUB_KEY") or (match.group(1) if match else None)


def portal_is_up() -> bool:
    try:
        return bool(portal_key()) and httpx.get(MANIFEST["base_url"] + "/api/hub/products", headers={"Authorization": f"Bearer {portal_key()}"}, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not portal_is_up(), reason="no portal key, or the portal is not answering")


def connect_portal(lane, key: str | None = None) -> Connection:
    connection = Connection(connection_id=PORTAL, name="Finebase Labs portal", purpose="website_chat", status="live",
                            manifest=Manifest.model_validate(MANIFEST), created_by="h-pamuditha")
    return conn_call.save(lane, conn_call.set_secret(lane, connection, "api_key", key or portal_key()))


def in_her_chat(lane, text: str) -> list[dict]:
    """The brain's messages in Amara's conversation with exactly this text, read from the portal."""
    messages = conn_call.call(lane, conn_call.load(lane, PORTAL), "conversation", {"conversation_id": AMARA_CHAT})["messages"]
    return [m for m in messages if m["sender"] != "customer" and m["body"] == text]


def tagged(text: str) -> str:
    return f"[brain test {uuid.uuid4().hex[:6]}] {text}"


def reply_action(text: str, run_id: str):
    return REFUND.model_copy(update={"run_id": run_id, "action_type": "reply_customer", "tool_id": "tool_reply_email", "arguments": {"message_plain": text}, "money": None})


# --- Amara's chat, one conversation

def amara_types(lane, text: str) -> None:
    """Her message as the portal's feed hands it over, through the real S1 inbound path."""
    message = {"id": f"test-{uuid.uuid4()}", "conversation_id": AMARA_CHAT, "sender": "customer", "body": text, "created_at": "2026-10-26T09:00:00Z", "conversations": {"customer_id": AMARA}}
    conn_inbound.take_in(lane, conn_call.load(lane, PORTAL), [message])
    lane.bus.drain()


def answer(text: str, waits: bool) -> dict:
    return {"tool": "reply_customer", "tool_input": {"message_plain": text, "awaits_customer": waits, "rationale_summary": "Talk to her in her chat.",
                                                     "citations": ["item_policy_window"], "confidence": 0.9}}


def test_each_visit_of_her_chat_gets_its_reply_in_the_real_portal():
    lane = full_lane()
    connect_portal(lane)
    lane.tooling["send_email"] = None  # as in production: no stand-in
    ask, close = tagged("Which order would you like refunded?"), tagged("Thanks. A person on our team will look at that order today.")
    lane.model, _ = scripted(answer(ask, True), answer(close, False))
    amara_types(lane, "I want a refund for my last order")
    amara_types(lane, "the Agent Gateway one")
    executed = [e.payload for e in lane.bus.topics["actions.executed"]]
    assert [(a["status"], a["error"]) for a in executed] == [("succeeded", None)] * 2 and list(runs(lane).values()) == [["awaiting_customer", "resolved"]]
    assert [m["id"] for m in in_her_chat(lane, ask)] == [executed[0]["external_ref"]] and [m["id"] for m in in_her_chat(lane, close)] == [executed[1]["external_ref"]]


# --- Once per key

def test_a_retry_with_the_same_key_never_posts_twice():
    lane = full_lane()
    connection, text = connect_portal(lane), tagged("Your refund is on its way.")
    first = tools_chat.send(lane, connection, AMARA_CHAT, {"message_plain": text}, "t:run_r:step_1")
    again = tools_chat.send(lane, connection, AMARA_CHAT, {"message_plain": text}, "t:run_r:step_1")
    assert first["status"] == again["status"] == "succeeded" and first["external_ref"] == again["external_ref"] and len(in_her_chat(lane, text)) == 1


@pytest.mark.skipif(bool(missing_infra(frozenset({"valkey"}))), reason="no Valkey")
def test_two_workers_on_the_same_reply_post_it_once():
    lane = full_lane(real_adapters(frozenset({"valkey"})))
    connection, text, key = connect_portal(lane), tagged("We have refunded your order."), f"t:run_{uuid.uuid4().hex[:6]}:step_1"
    results, start = [None, None], threading.Barrier(2)
    def worker(index):
        start.wait()
        tools = {**lane.tooling, "runners": {"chat": lambda tool_id, arguments, k: tools_chat.send(lane, connection, AMARA_CHAT, arguments, k)}, "sleep": time.sleep}  # the real backoff
        results[index] = stages_act.act(reply_action(text, key.split(":")[1]), EXECUTE, None, "t", tools, lane.new_id, lane.now)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert [r.status for r in results] == ["succeeded"] * 2 and results[0].external_ref == results[1].external_ref and len(in_her_chat(lane, text)) == 1


def test_an_answer_lost_after_the_post_is_found_not_posted_again(monkeypatch):
    lane = full_lane()
    connection, text, real = connect_portal(lane), tagged("Done: your refund is filed."), conn_call.http
    lost = []
    def post_then_lose(request: httpx.Request) -> httpx.Response:
        answer = real.send(httpx.Request(request.method, request.url, headers=request.headers, content=request.content))
        if request.method == "POST" and not lost:
            lost.append(1)
            raise httpx.ReadTimeout("answer lost", request=request)
        headers = {k: v for k, v in answer.headers.items() if k.lower() not in ("content-encoding", "content-length")}  # already decoded
        return httpx.Response(answer.status_code, headers=headers, content=answer.content)
    monkeypatch.setattr(conn_call, "http", httpx.Client(transport=httpx.MockTransport(post_then_lose)))
    tools = {**tooling(), "runners": {"chat": lambda tool_id, arguments, key: tools_chat.send(lane, connection, AMARA_CHAT, arguments, key)}}
    result = stages_act.act(reply_action(text, "run_lost"), EXECUTE, None, "t", tools, lane.new_id, lane.now)
    assert result.status == "succeeded" and len(in_her_chat(lane, text)) == 1 and result.external_ref == in_her_chat(lane, text)[0]["id"]


def forwarding(fail_first_post_with):
    """A client that sends every call to the real portal, except the first POST, which fails before it is sent."""
    real, failed = conn_call.http, []
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and not failed:
            failed.append(1)
            raise fail_first_post_with("no answer", request=request)
        answer = real.send(httpx.Request(request.method, request.url, headers=request.headers, content=request.content))
        headers = {k: v for k, v in answer.headers.items() if k.lower() not in ("content-encoding", "content-length")}
        return httpx.Response(answer.status_code, headers=headers, content=answer.content)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_an_identical_reply_from_days_ago_is_not_taken_for_this_one(monkeypatch):
    lane = full_lane()
    connection, old = connect_portal(lane), "Hi! Got your messages loud and clear. How can I help?"  # the brain said this on 19 October
    before = [m["id"] for m in in_her_chat(lane, old)]
    monkeypatch.setattr(conn_call, "http", forwarding(httpx.ConnectError))
    tools = {**tooling(), "runners": {"chat": lambda tool_id, arguments, key: tools_chat.send(lane, connection, AMARA_CHAT, arguments, key)}}
    result = stages_act.act(reply_action(old, f"run_{uuid.uuid4().hex[:6]}"), EXECUTE, None, "t", tools, lane.new_id, lane.now)
    now = [m["id"] for m in in_her_chat(lane, old)]
    assert result.status == "succeeded" and len(now) == len(before) + 1 and result.external_ref not in before


def test_a_refused_key_posts_nothing_and_a_person_is_told():
    lane, reader = full_lane(), full_lane()
    connect_portal(reader)
    text = tagged("This must never appear.")
    result = tools_chat.send(lane, connect_portal(lane, key="fbl_wrong"), AMARA_CHAT, {"message_plain": text}, "t:run_bad:step_1")
    assert result["error"] == {"code": "chat_refused", "retryable": False} and in_her_chat(reader, text) == []
