# test_s1_refund_bdd.py: S1 Capture for the refund BDD, tested only at its boundary: portal messages go in, K1 comes out
# on signals.raw. Lines: "the shop website chat is connected", "Amara types 'I want a refund for my last order'",
# "Amara answers 'yes, that one'". Then the contract, a golden K1, rules that always hold, and unhappy paths.
# Uses: conn_call.py, conn_inbound.py, observe.py, orchestrate.py, contracts_signal.py, samples/findbase_portal_manifest.json.
import hashlib
import json
import random
from pathlib import Path

import httpx
import pytest

from app.pipeline import conn_call, conn_inbound, fakes, observe, orchestrate
from app.pipeline.conn_call import Connection
from app.pipeline.conn_spec import Manifest
from app.pipeline.contracts_signal import RawSignalEnvelope
from tests.golden import NOW, SEED

# Config
CONNECTION_ID = "conn-shop-chat"
KEY = "test-only-portal-key"
MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "samples" / "findbase_portal_manifest.json").read_text())
REFUND_ASK = "I want a refund for my last order"
CONFIRM = "yes, that one"


def portal_message(seq: int, body: str, sender: str = "customer", **overrides) -> dict:
    """One message as the portal's hub API sends it."""
    message = {"id": f"m-{seq}", "conversation_id": "c-1", "seq": seq, "sender": sender, "body": body,
               "created_at": "2026-10-20T09:00:00Z", "conversations": {"customer_id": "cust-amara"}}
    return {**message, **overrides}


@pytest.fixture
def shop(monkeypatch):
    """Given the shop website chat is connected: a live connection whose portal answers from `inbox`."""
    inbox: list[dict] = []

    def portal(request: httpx.Request) -> httpx.Response:
        since = int(request.url.params.get("since", 0))
        new = [m for m in inbox if m["seq"] > since]
        return httpx.Response(200, json={"messages": new, "nextSince": max([since] + [m["seq"] for m in new])})

    monkeypatch.setattr(conn_call, "http", httpx.Client(transport=httpx.MockTransport(portal)))
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    connection = Connection(connection_id=CONNECTION_ID, name="Shop website", purpose="website_chat", status="live",
                            manifest=Manifest.model_validate(MANIFEST), created_by="h-pamuditha")
    conn_call.set_secret(lane, conn_call.save(lane, connection), "api_key", KEY)
    return lane, inbox


def poll(lane) -> list[RawSignalEnvelope]:
    """Run one S1 poll and return every K1 on signals.raw so far."""
    conn_inbound.poll_once(lane, conn_call.load(lane, CONNECTION_ID))
    return [RawSignalEnvelope.model_validate(e.payload) for e in lane.bus.topics.get("signals.raw", [])]


def stored_body(lane, k1: RawSignalEnvelope) -> dict:
    return json.loads(lane.object_store[k1.raw_object_uri])


# --- BDD: the happy path

def test_amara_asks_for_a_refund_and_s1_captures_it(shop):
    lane, inbox = shop
    # When Amara types "I want a refund for my last order" (the agent's greeting is not hers, so it is skipped)
    inbox += [portal_message(1, REFUND_ASK), portal_message(2, "Hello", sender="agent")]
    k1s = poll(lane)
    # Then exactly one K1, with her words stored once and her conversation as the session
    assert len(k1s) == 1
    assert k1s[0].external_id == "m-1" and k1s[0].source_type == "chat" and k1s[0].headers_subset == {"session": "c-1"}
    assert stored_body(lane, k1s[0])["text"] == REFUND_ASK


def test_amara_confirms_and_s1_captures_it_on_the_same_session(shop):
    lane, inbox = shop
    inbox.append(portal_message(1, REFUND_ASK))
    poll(lane)
    # And Amara answers "yes, that one"
    inbox.append(portal_message(3, CONFIRM))
    k1s = poll(lane)
    assert [k.external_id for k in k1s] == ["m-1", "m-3"]
    assert {k.headers_subset["session"] for k in k1s} == {"c-1"}
    assert stored_body(lane, k1s[1])["text"] == CONFIRM


# --- Contract: K1 is what S2 reads, and the seam log matches it

def test_k1_matches_the_golden_master(shop):
    lane, inbox = shop
    inbox.append(portal_message(1, REFUND_ASK))
    k1 = poll(lane)[0].model_dump(mode="json")
    body = json.dumps({"text": REFUND_ASK, "customer_ref": "cust-amara", "visitor_name": None, "visitor_email": None}).encode()
    assert k1 == {
        "connector_id": CONNECTION_ID, "grant_id": f"grant_{CONNECTION_ID}", "source_type": "chat", "external_id": "m-1",
        "received_at": NOW.isoformat().replace("+00:00", "Z"), "signature_verified": True,
        "raw_object_uri": f"s3://brain/{SEED['tenant_id']}/raw/{NOW:%Y/%m/%d}/{CONNECTION_ID}/m-1.json",
        "raw_sha256": hashlib.sha256(body).hexdigest(), "content_type": "application/json",
        "size_bytes": len(body), "headers_subset": {"session": "c-1"},
    }


def test_the_seam_log_records_what_came_in_and_went_out(shop, tmp_path, monkeypatch):
    lane, inbox = shop
    monkeypatch.setattr(observe, "SEAM_LOG_DIR", str(tmp_path))
    inbox.append(portal_message(1, REFUND_ASK))
    k1 = poll(lane)[0]
    line = json.loads((tmp_path / "S1.jsonl").read_text().splitlines()[0])
    assert RawSignalEnvelope.model_validate(line["out"]) == k1  # the out side is exactly the contract S2 reads
    assert line["in"]["external_id"] == "m-1" and "raw_body" not in line["in"]  # the log never holds her words


# --- Rules that always hold, over many random inboxes

@pytest.mark.parametrize("seed", range(30))
def test_rules_hold_for_any_inbox(shop, seed):
    lane, inbox = shop
    picker = random.Random(seed)
    for seq in range(1, picker.randint(1, 12)):
        inbox.append(portal_message(seq, picker.choice([REFUND_ASK, CONFIRM, "ok", "é ✓"]), sender=picker.choice(["customer", "agent"])))
    k1s = poll(lane)
    customer_ids = [m["id"] for m in inbox if m["sender"] == "customer"]
    # Every customer message gives one K1, none is lost, and each stored body matches its hash
    assert [k.external_id for k in k1s] == customer_ids
    assert all(hashlib.sha256(lane.object_store[k.raw_object_uri]).hexdigest() == k.raw_sha256 for k in k1s)


# --- Unhappy paths

def test_a_message_without_an_id_is_skipped_not_stored_as_none(shop):
    lane, inbox = shop
    inbox += [portal_message(1, REFUND_ASK, id=None), portal_message(2, CONFIRM)]
    assert [k.external_id for k in poll(lane)] == ["m-2"]


def test_a_message_without_a_conversation_has_no_session(shop):
    lane, inbox = shop
    inbox.append(portal_message(1, REFUND_ASK, conversation_id=None))
    assert poll(lane)[0].headers_subset == {}


def test_redelivery_lands_on_the_same_object(shop):
    lane, inbox = shop
    inbox.append(portal_message(1, REFUND_ASK))
    first = poll(lane)[0]
    conn_inbound.take_in(lane, conn_call.load(lane, CONNECTION_ID), [inbox[0]])  # a push of the same message
    assert len(lane.object_store) == 1 and lane.bus.topics["signals.raw"][1].payload["raw_object_uri"] == first.raw_object_uri
