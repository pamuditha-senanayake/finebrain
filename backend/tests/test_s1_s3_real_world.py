# test_s1_s3_real_world.py: the real-world gaps found when S1 to S3 were checked against the CLAUDE.md "ready for real use"
# list. Two chat tools that both number from 1, a message id that tries to shape a path, a publish that fails after the
# dedup claim, and a crash between S3 publishing a task and marking the message handled.
# Uses: capture_api.py, orchestrate.py, stages_orchestrate.py, stages_route.py, tests/test_s1_refund_chat.py.
import json

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate, stages_orchestrate
from tests.golden import NOW, SEED, raw_sample
from tests.test_s1_refund_chat import CHAT, FIRST, SESSION

# Config
APP_CHAT = "conn_app_chat"  # a second chat tool on the same tenant, e.g. the mobile app
TWO_CHATS = {**SEED, "connectors": {**SEED["connectors"], APP_CHAT: {**SEED["connectors"][CHAT], "grant_id": "grant_app_chat_read", "secret": "test-only-secret-app"}}}


# --- Helpers

def make_lane(seed=TWO_CHATS):
    observe.reset_counts()
    return orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)


def post(lane, connector: str, message: dict, email: str | None = "anna@example.lk", session: str = SESSION) -> int:
    """One chat message from one connector's webhook, then the consumers catch up."""
    body = json.dumps({"visitor_name": "Visitor", "visitor_email": email, "text": message["text"], "sent_at": "2026-10-10T09:55:00+05:30"}).encode()
    headers = {"content-type": "application/json", "x-external-id": message["id"], "session": session,
               "x-signature": capture_api.sign(lane.seed["connectors"][connector]["secret"], body)}
    status = TestClient(capture_api.create_app(lane)).post(f"/capture/{connector}", content=body, headers=headers).status_code
    lane.bus.drain()
    return status


def payloads(lane, topic: str) -> list[dict]:
    return [envelope.payload for envelope in lane.bus.topics.get(topic, [])]


# --- S1 and S2: two chat tools that both number their messages from 1

def test_the_same_message_id_on_two_connectors_is_two_messages():
    lane = make_lane()
    post(lane, CHAT, {"id": "m-1", "text": "I want a refund for my last order"})
    post(lane, APP_CHAT, {"id": "m-1", "text": "where is my parcel?"})
    raw = payloads(lane, "signals.raw")
    bodies = [lane.object_store[k1["raw_object_uri"]] for k1 in raw]
    assert len({k1["raw_object_uri"] for k1 in raw}) == 2 and bodies[0] != bodies[1]  # neither overwrites the other
    signals = payloads(lane, "signals.normalized")
    assert len(signals) == 2 and observe.read_count("s2.duplicate") == 0  # the second is not dropped as a duplicate


def test_two_anonymous_visitors_with_one_session_id_on_two_connectors_stay_two_customers():
    lane = make_lane()
    post(lane, CHAT, {"id": "w-1", "text": "hello"}, email=None, session="s-1")
    post(lane, APP_CHAT, {"id": "a-1", "text": "hello"}, email=None, session="s-1")
    first, second = payloads(lane, "signals.normalized")
    assert first["actor"]["ref"] != second["actor"]["ref"] and first["conversation_id"] != second["conversation_id"]


def test_a_message_id_cannot_shape_the_storage_path():
    lane = make_lane()
    assert post(lane, CHAT, {"id": "../../graph/x", "text": "I want a refund for my last order"}) == 202
    [k1] = payloads(lane, "signals.raw")
    assert k1["raw_object_uri"] == "s3://brain/finebase_labs/raw/2026/10/10/conn_web_chat/..%2F..%2Fgraph%2Fx.json"


# --- S2: a publish that fails after the dedup claim

def test_a_failed_publish_after_the_claim_does_not_lose_the_message(monkeypatch):
    lane = make_lane()
    publish = lane.bus.publish

    def broker_down_for_k2(topic, *args, **kwargs):
        if topic == "signals.normalized":
            raise ConnectionError("broker down")
        return publish(topic, *args, **kwargs)

    monkeypatch.setattr(lane.bus, "publish", broker_down_for_k2)
    post(lane, CHAT, FIRST)
    assert lane.bus.dead_letters("signals.raw") and "signals.normalized" not in lane.bus.topics
    monkeypatch.setattr(lane.bus, "publish", publish)
    lane.bus.redeliver("signals.raw", lane.bus.topics["signals.raw"][0])  # Kafka delivers it again
    lane.bus.drain()
    assert len(payloads(lane, "signals.normalized")) == 1  # the claim was released, so the redelivery went through


# --- S3: a crash between publishing the task and marking the message handled

@pytest.mark.parametrize("sample", ["s2", "s3"])
def test_a_redelivered_signal_gives_the_same_task_and_one_run(sample):
    lane = make_lane(SEED)
    lane.bus.subscribers["tasks.created"] = [("worker", "S4", lambda envelope: stages_orchestrate.begin_run(lane, envelope))]
    orchestrate.capture_signal(lane, raw_sample(sample))  # an email refund: no chat, so only the task id can catch a repeat
    lane.bus.drain()
    k2 = lane.bus.topics["signals.normalized"][0]
    lane.bus.handled.discard(f"resolver:{k2.event_id}")  # S3 published its task, then crashed before marking K2 handled
    lane.bus.redeliver("signals.normalized", k2)
    lane.bus.drain()
    tasks = payloads(lane, "tasks.created")
    assert len(tasks) == 2 and tasks[0]["task_id"] == tasks[1]["task_id"]  # the same task, twice
    assert len(payloads(lane, "runs.started")) == 1  # S4 starts it once, so the customer is never refunded twice
