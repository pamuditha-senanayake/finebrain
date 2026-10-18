# test_api_brain.py: Ask the Brain and Sensors on the Finebase HQ API (step 9b). Ask reads with the person's own
# rights, cites only what it was given, logs the read, always knows who it is (cold start), and remembers the
# conversation; Sensors come from connectors and S1's counters.
# Uses: app/api/routes.py, ask.py, ask_memory.py, self_knowledge.py, hq.py (load_hq), capture_api.py, tests/golden.py.
import pytest
from fastapi.testclient import TestClient

from app.api import ask, self_knowledge
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

def fake_answerer(question: str, documents: list[tuple[str, str]], history=()) -> tuple[str, list[str]]:
    return "Customers have 30 days.", [documents[0][0], "item_made_up"]


class Recorder:
    """An answerer that keeps what it was given, so tests can see the documents and the earlier turns."""

    def __init__(self):
        self.calls = []

    def __call__(self, question, documents, history=()):
        self.calls.append({"question": question, "ids": [item_id for item_id, _ in documents], "history": list(history)})
        return f"Noted: {question}", []


def build(answerer=fake_answerer):
    observe.reset_counts()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    return TestClient(create_api_app(lane, HQ, answerer)), lane


def post_ask(client, question: str = QUESTION, persona: str = FOUNDER, page: dict | None = None, conversation: str | None = None):
    return client.post(f"/api/t/{TENANT}/ask", json={"question": question, "page": page, "conversationId": conversation}, headers={"x-persona": persona})


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


# --- Cold start and memory

def test_self_knowledge_is_public_knowledge_in_the_hq_seed():
    mine = [item for item in SEED["knowledge"] if item["source"]["document_id"] == self_knowledge.DOCUMENT_ID]
    assert len(mine) >= 5 and all(item["sensitivity"] == "public" and item["kind"] == "chunk" for item in mine)


def test_who_i_am_goes_with_every_question():
    answerer = Recorder()
    client, _ = build(answerer)
    post_ask(client, "hello, what can you do?")
    assert self_knowledge.OVERVIEW_ID in answerer.calls[0]["ids"]


def test_conversation_is_remembered_and_only_for_its_owner():
    answerer = Recorder()
    client, _ = build(answerer)
    first = post_ask(client, "My favourite colour is teal.").json()
    second = post_ask(client, "What is my favourite colour?", conversation=first["conversationId"]).json()
    assert second["conversationId"] == first["conversationId"]
    assert answerer.calls[1]["history"] == [("My favourite colour is teal.", "Noted: My favourite colour is teal.")]
    turns = client.get(f"/api/t/{TENANT}/ask/turns?conversation={first['conversationId']}", headers={"x-persona": FOUNDER}).json()
    assert [t["question"] for t in turns] == ["My favourite colour is teal.", "What is my favourite colour?"]
    assert set(turns[0]) == {"question", "answer", "at"}
    other = client.get(f"/api/t/{TENANT}/ask/turns?conversation={first['conversationId']}", headers={"x-persona": "h-udayanga"})
    assert other.status_code == 403
    assert post_ask(client, "hi", persona="h-udayanga", conversation=first["conversationId"]).status_code == 403


def test_new_conversation_has_no_history():
    answerer = Recorder()
    client, _ = build(answerer)
    post_ask(client, "first")
    post_ask(client, "second")
    assert answerer.calls[1]["history"] == []


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
