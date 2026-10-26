# test_l3_conversations.py: what people see of the pipeline's chats. L3 Conversations shows every chat with each
# visitor message and every reply (the agent's, a notice, a person's); a person can take a chat over (the agent stays
# out), reply into the real chat, hand it back, and close it on the site too; an escalation shows in Escalations; Fleet,
# Skills and Policies show what Studio made; Ask the Brain answers from the graph. Uses: tests/activity_world.py, api/*.
import uuid

import pytest

from app.api import ask as asking
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.activity_world import WF, answer_with, build, build_landing, stand_in_portal, visitor
from tests.s6_world import scripted
from tests.test_activity_bdd import escalate
from tests.test_s5_real import S5_PARTS, parts

# Config
CHAT = "conn_landing_chat:c-landing-1"


def get(client, lane, resource: str):
    return client.get(f"/api/t/{lane.seed['tenant_id']}/{resource}", headers={"x-persona": "h-pamuditha"})


def op(client, lane, name: str, body: dict):
    return client.post(f"/api/t/{lane.seed['tenant_id']}/ops/{name}", json=body, headers={"x-persona": "h-pamuditha"})


def landing(monkeypatch, *answers, calls=None):
    client, lane = build()
    posted = stand_in_portal(monkeypatch, calls)
    ids = build_landing(client, lane)
    lane.model, _ = scripted(*(a(ids) for a in answers))
    return client, lane, ids, posted


# --- L3 Conversations, every visit

def test_a_visitors_chat_shows_each_message_and_reply_in_l3(monkeypatch):
    client, lane, ids, _ = landing(monkeypatch, lambda i: answer_with(i["policy"], "Which product?", waits=True), lambda i: answer_with(i["policy"], "A person will book it."))
    visitor(lane, "Can I see a demo?")
    shown = get(client, lane, f"conversations/{CHAT}").json()
    assert (shown["status"], shown["agentId"], [m["from"] for m in shown["messages"]]) == ("agent", ids["agent"], ["customer", "agent"])  # waiting for her answer
    visitor(lane, "The Agent Gateway")
    shown = get(client, lane, f"conversations/{CHAT}").json()
    assert [m["text"] for m in shown["messages"]] == ["Can I see a demo?", "Which product?", "The Agent Gateway", "A person will book it."]
    assert shown["status"] == "closed" and shown["reasoningSummary"] and [c["id"] for c in get(client, lane, "conversations").json()] == [CHAT]


def test_an_escalation_shows_in_escalations_and_its_notice_in_the_chat(monkeypatch):
    client, lane, ids, _ = landing(monkeypatch, lambda i: escalate(i["policy"]))
    visitor(lane, "Can I get a 20% discount?")
    assert [m["from"] for m in get(client, lane, f"conversations/{CHAT}").json()["messages"]] == ["customer", "system"]
    assert any(e["agentId"] == ids["agent"] for e in get(client, lane, "escalations").json())


# --- A person takes the chat

def test_a_person_takes_over_replies_and_hands_back(monkeypatch):
    client, lane, ids, posted = landing(monkeypatch, lambda i: answer_with(i["policy"], "Hello!"), lambda i: answer_with(i["policy"], "Back with the agent."))
    visitor(lane, "Hi")
    assert op(client, lane, "sendMessage", {"conversationId": CHAT, "text": "Hi from Pamuditha"}).status_code == 409  # take it over first
    assert op(client, lane, "takeover", {"conversationId": CHAT}).json()["takenOverBy"] == "h-pamuditha"
    visitor(lane, "Is anyone there?")  # the agent stays out
    assert op(client, lane, "sendMessage", {"conversationId": CHAT, "text": "Yes, I am here."}).status_code == 200
    assert [p["body"] for p in posted] == ["Hello!", "Yes, I am here."]  # the person's reply went into the real chat
    op(client, lane, "handback", {"conversationId": CHAT})
    visitor(lane, "Thanks")
    shown = get(client, lane, f"conversations/{CHAT}").json()
    assert [m["from"] for m in shown["messages"]] == ["customer", "agent", "customer", "human", "customer", "agent"]


def test_closing_closes_it_on_the_site_too(monkeypatch):
    calls = []
    client, lane, _, _ = landing(monkeypatch, lambda i: answer_with(i["policy"]), calls=calls)
    visitor(lane, "Hi")
    assert op(client, lane, "closeConversation", {"conversationId": CHAT, "note": "Done"}).json()["status"] == "closed"
    assert ("PATCH", "/api/hub/conversations/c-landing-1") in calls


# --- Fleet, Skills, Policies and Ask show what Studio made

def test_fleet_skills_and_policies_show_what_studio_made():
    client, lane = build()
    ids = build_landing(client, lane)
    agent = next(a for a in get(client, lane, "agents").json() if a["id"] == ids["agent"])
    skill = next(s for s in get(client, lane, "skills").json() if s["id"] == ids["skill"])
    policy = next(p for p in get(client, lane, "policies").json() if p["key"] == ids["policy"])
    assert (agent["name"], agent["policies"], skill["name"], skill["policies"]) == ("Landing assistant", [ids["policy"]], "Answer landing visitors", [ids["policy"]])
    assert (policy["name"], [d["id"] for d in policy["dependents"]]) == ("No price promises in chat", [ids["skill"]])


def test_ask_the_brain_answers_from_the_graph():
    client, lane = build()
    build_landing(client, lane)
    seen = {}
    def answerer(question, items, history, address):
        seen.update(dict(items))
        return "Landing assistant owns Landing page chat.", ["work_map"]
    answer = asking.ask(lane, answerer, "h-pamuditha", "Who handles the landing page chat?", None, None)
    assert "Owner: Landing assistant" in seen["work_map"] and "Listens to: Landing chat" in seen["work_map"]
    assert [(c.id, c.href) for c in answer.citations] == [("work_map", "/studio")]


# --- The same on real infra

@pytest.mark.skipif(bool(missing_infra(S5_PARTS)), reason="infra not answering")
def test_l3_shows_the_chat_and_a_takeover_holds_on_real_infra(monkeypatch):
    tag = uuid.uuid4().hex[:8]
    client, lane = build(real_adapters(parts(), topic_prefix=f"l3{tag}."), tenant=f"test_l3_{tag}")
    try:
        posted = stand_in_portal(monkeypatch)
        ids = build_landing(client, lane)
        lane.model, _ = scripted(answer_with(ids["policy"], "Hello!"))
        visitor(lane, "Hi")
        op(client, lane, "takeover", {"conversationId": CHAT})
        visitor(lane, "Anyone?")
        shown = get(client, lane, f"conversations/{CHAT}").json()  # from Postgres records
        assert ([m["from"] for m in shown["messages"]], shown["status"], [p["body"] for p in posted]) == (["customer", "agent", "customer"], "human", ["Hello!"])
    finally:
        delete_prefixed_topics(f"l3{tag}.")
