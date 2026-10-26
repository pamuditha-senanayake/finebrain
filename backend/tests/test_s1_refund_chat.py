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
    "raw_sha256": "db71bf623ae3a954cf2f729525ab28dbd33e400028c6d05ac810e2ec07f41620", "size_bytes": 145, "headers_subset": {"session": SESSION},
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
    return json.dumps({"visitor_name": "Anna", "visitor_email": "anna@example.lk", "text": message["text"], "sent_at": "2026-10-10T09:55:00+05:30"}).encode()


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


# --- Seam logs: what came in and what went out, matching K1, with no personal data

def test_seam_logs_record_what_came_in_and_went_out(client, lane, caplog):
    with caplog.at_level(logging.INFO, logger=observe.LOGGER_NAME):
        send(client, FIRST)
    lines = [json.loads(record.message) for record in caplog.records]
    seam_in = next(line for line in lines if line["event"] == "seam_in")
    seam_out = next(line for line in lines if line["event"] == "seam_out")
    k1 = k1_events(lane)[0]
    assert (seam_in["connector_id"], seam_in["external_id"], seam_in["content_type"]) == (CHAT, FIRST["id"], "application/json")
    assert {key: seam_out[key] for key in K1_FIELDS if key in seam_out} == {key: k1[key] for key in seam_out if key in K1_FIELDS}
    assert "Anna" not in caplog.text and "anna@example" not in caplog.text and "refund for my last order" not in caplog.text


# --- Rules that always hold (the exact output varies, these never do)

def test_rules_hold_for_random_traffic(client, lane):
    """Random mix of good and bad messages: nothing is lost, nothing is invented, refusals store nothing."""
    generator = random.Random(2026)  # fixed seed so a failure can be replayed
    sent_ok = []
    for number in range(200):
        message = {"id": f"chat_msg_{number}", "text": "x" * generator.randint(0, 500)}
        bad = generator.choice([None, "secret", "type", "connector"])
        kwargs = {"secret": "wrong"} if bad == "secret" else {"content_type": "image/png"} if bad == "type" else {"connector_id": "conn_nobody"} if bad == "connector" else {}
        status = send(client, message, **kwargs).status_code
        sent_ok += [message["id"]] if status == 202 else []
    events = k1_events(lane)
    assert [event["external_id"] for event in events] == sent_ok  # none lost, none invented, order kept
    assert len(lane.object_store) == len(events) <= 200
    assert all(event["signature_verified"] for event in events)


# --- Golden master: Anna's first message must keep producing exactly this

def test_first_message_matches_the_frozen_result(client, lane):
    send(client, FIRST)
    k1 = k1_events(lane)[0]
    assert {key: k1[key] for key in FROZEN_FIRST} == FROZEN_FIRST


# --- Redelivery: the same chat message sent twice is stored once and S2 keeps one copy

def test_same_chat_message_twice_is_stored_once_and_normalized_once(client, lane):
    lane.bus.subscribers = {"signals.raw": lane.bus.subscribers["signals.raw"]}  # S1 and S2 only
    assert send(client, FIRST).status_code == send(client, FIRST).status_code == 202
    lane.bus.drain()
    assert len(lane.object_store) == 1
    assert len({event["raw_sha256"] for event in k1_events(lane)}) == 1
    assert len(lane.bus.topics["signals.normalized"]) == 1
