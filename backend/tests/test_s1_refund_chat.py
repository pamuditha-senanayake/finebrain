# test_s1_refund_chat.py: S1 for the refund happy path BDD (website chat). Only the S1 lines of the scenario.
# Covers: BDD acceptance, seam logs (contract K1), rules that always hold, a frozen golden master, random inputs.
# Uses: capture_api.py, orchestrate.py, observe.py, tests/golden.py. Run: uv run pytest tests/test_s1_refund_chat.py
import json
import logging
import random

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate
from tests.golden import NOW, SEED

# Config
CHAT = "conn_web_chat"
SESSION = "chat_sess_anna"
FIRST = {"id": "chat_msg_anna_1", "text": "I want a refund for my last order"}
SECOND = {"id": "chat_msg_anna_2", "text": "yes, that one"}
FROZEN_FIRST = {  # reviewed by hand once, then frozen
    "raw_object_uri": "s3://brain/finebase_labs/raw/2026/10/10/chat_msg_anna_1.json",
    "raw_sha256": "4ac87e7c39b64d40a711fcee3890c7461eae40f1fa707c9736477d8b3e6b03f9", "size_bytes": 109, "headers_subset": {"session": SESSION},
}
K1_FIELDS = ("connector_id", "grant_id", "source_type", "external_id", "raw_object_uri", "raw_sha256", "size_bytes", "content_type")


# --- Helpers

@pytest.fixture
def lane():
    observe.reset_counts()
    return orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)


@pytest.fixture
def client(lane):
    return TestClient(capture_api.create_app(lane))


def chat_body(message: dict) -> bytes:
    return json.dumps({"visitor_name": "Anna", "text": message["text"], "sent_at": "2026-10-10T09:55:00+05:30"}).encode()


def send(client, message=FIRST, connector_id=CHAT, body=None, secret=None, content_type="application/json"):
    """Post one chat message the way the website chat webhook would."""
    body = chat_body(message) if body is None else body
    secret = secret or SEED["connectors"].get(connector_id, {}).get("secret", "none")
    headers = {"content-type": content_type, "x-external-id": message["id"], "session": SESSION, "x-signature": capture_api.sign(secret, body)}
    return client.post(f"/capture/{connector_id}", content=body, headers=headers)


def k1_events(lane) -> list[dict]:
    return [envelope.payload for envelope in lane.bus.topics.get("signals.raw", [])]


# --- BDD: the S1 lines of the scenario

def test_given_chat_is_connected_when_anna_types_then_the_message_is_captured(client, lane):
    """Given the shop chat is connected, when Anna types her refund request, then one raw message is stored and published."""
    response = send(client, FIRST)
    assert response.status_code == 202
    assert len(lane.object_store) == 1 and len(k1_events(lane)) == 1
    assert k1_events(lane)[0]["external_id"] == FIRST["id"] and k1_events(lane)[0]["source_type"] == "chat"


def test_when_anna_answers_yes_then_it_is_a_second_message_in_the_same_session(client, lane):
    """The 'yes, that one' reply is its own raw message, tied to the same chat session."""
    send(client, FIRST)
    send(client, SECOND)
    events = k1_events(lane)
    assert [event["external_id"] for event in events] == [FIRST["id"], SECOND["id"]]
    assert {event["headers_subset"]["session"] for event in events} == {SESSION}
    assert len(lane.object_store) == 2
