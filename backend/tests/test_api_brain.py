# test_api_brain.py: Ask the Brain and Sensors on the Finebase HQ API (step 9b). Ask reads with the person's own
# rights, cites only what it was given, and logs the read; Sensors come from connectors and S1's counters.
# Uses: app/api/routes.py, app/api/ask.py, app/api/hq.py (load_hq), capture_api.py, stages_retrieve.py, tests/golden.py.
import pytest
from fastapi.testclient import TestClient

from app.api import ask
from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import capture_api, fakes, observe, orchestrate, stages_retrieve
from tests.golden import NOW, RAW, recorded_answers

# Config
SEED, HQ = load_hq()
TENANT = SEED["tenant_id"]
FOUNDER = "h-pamuditha"
QUESTION = "How many days do customers have to ask for a refund?"


# --- Helpers

def fake_answerer(question: str, documents: list[tuple[str, str]]) -> tuple[str, list[str]]:
    return "Customers have 30 days.", [documents[0][0], "item_made_up"]


def build(answerer=fake_answerer):
    observe.reset_counts()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    return TestClient(create_api_app(lane, HQ, answerer)), lane


def post_ask(client, question: str = QUESTION, persona: str = FOUNDER, page: dict | None = None):
    return client.post(f"/api/t/{TENANT}/ask", json={"question": question, "page": page}, headers={"x-persona": persona})


# --- Ask the Brain

def test_answer_cites_only_offered_documents_and_logs_the_read():
    client, lane = build()
    body = post_ask(client, page={"path": "/l1/ask", "scope": "system"}).json()
    assert body["answer"] == "Customers have 30 days." and body["scope"] == "system"
    assert [c["id"] for c in body["citations"]] != [] and all(c["id"] != "item_made_up" for c in body["citations"])
    assert set(body["citations"][0]) == {"id", "kind", "label", "validFrom", "validTo", "href"}
    lane.bus.drain()
    reads = client.get(f"/api/t/{TENANT}/access-decisions?principal={FOUNDER}", headers={"x-persona": FOUNDER}).json()
    assert any(r["action"] == "kb.read" for r in reads)


def test_without_claude_it_lists_the_closest_documents():
    client, _ = build(answerer=None)
    body = post_ask(client).json()
    assert body["answer"] == ask.NO_CLAUDE_NOTE and len(body["citations"]) >= 1 and body["withheld"] >= 0


@pytest.mark.parametrize("question, persona, status", [("  ", FOUNDER, 400), (QUESTION, "h-stranger", 401)])
def test_bad_requests(question, persona, status):
    client, _ = build()
    assert post_ask(client, question, persona).status_code == status


def test_store_outage_answers_503(monkeypatch):
    client, _ = build()

    def broken(*args, **kwargs):
        raise stages_retrieve.ContextUnavailable("ConnectionError")

    monkeypatch.setattr(stages_retrieve, "retrieve", broken)
    assert post_ask(client).json() == {"error": "knowledge_unavailable"}


# --- Sensors

def test_sensors_show_connectors_with_their_activity():
    client, lane = build()
    body = RAW["s2_refund_monthly_in_policy"]["raw_body"].encode()
    headers = {"content-type": "message/rfc822", "x-external-id": "ext-sensor-1", "x-signature": capture_api.sign(SEED["connectors"]["conn_gmail_support"]["secret"], body)}
    assert client.post("/capture/conn_gmail_support", content=body, headers=headers).status_code == 202
    sensors = {s["id"]: s for s in client.get(f"/api/t/{TENANT}/sensors", headers={"x-persona": FOUNDER}).json()}
    assert set(sensors) == {"conn_gmail_support", "conn_web_chat", "conn_upload_console"}
    inbox = sensors["conn_gmail_support"]
    assert (inbox["name"], inbox["health"], inbox["eventsPerHour"], inbox["personalData"]) == ("Support inbox", "ok", 1.0, True)
    assert observe.read_last_seen("s1.last_event.conn_gmail_support") == inbox["lastEventAt"] and sensors["conn_web_chat"]["eventsPerHour"] == 0
