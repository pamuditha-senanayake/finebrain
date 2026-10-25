# test_ask_history.py: the Ask history. A person sees only their own chats, newest first, each named by its first
# question, and an old chat still loads its turns to be continued.
# Uses: tests/test_api_brain.py (build, post_ask), app/api/ask_memory.py.
from datetime import timedelta

from tests.test_api_brain import FOUNDER, TENANT, Recorder, build, post_ask


# --- Helpers

def history(client, persona: str = FOUNDER) -> list[dict]:
    return client.get(f"/api/t/{TENANT}/ask/conversations", headers={"x-persona": persona}).json()


# --- The history

def test_history_lists_my_chats_newest_first_with_titles():
    client, lane = build(Recorder())
    first = post_ask(client, "What is the refund window for customers who paid by card?").json()
    post_ask(client, "And for cash?", conversation=first["conversationId"])
    lane.now += timedelta(hours=5)
    second = post_ask(client, "Who approved the last refund?").json()

    listed = history(client)
    assert [chat["id"] for chat in listed] == [second["conversationId"], first["conversationId"]]
    assert listed[1] == {"id": first["conversationId"], "title": "What is the refund window for customers…", "at": listed[1]["at"], "turns": 2}
    assert listed[0]["title"] == "Who approved the last refund?"


def test_history_shows_only_my_own_chats():
    client, _ = build(Recorder())
    post_ask(client, "mine")
    post_ask(client, "theirs", persona="h-udayanga")
    assert [chat["title"] for chat in history(client)] == ["mine"]
    assert [chat["title"] for chat in history(client, "h-udayanga")] == ["theirs"]


def test_an_old_chat_loads_and_continues():
    answerer = Recorder()
    client, _ = build(answerer)
    old = post_ask(client, "My favourite colour is teal.").json()["conversationId"]
    post_ask(client, "Something else entirely.")
    post_ask(client, "What is my favourite colour?", conversation=old)
    assert answerer.calls[2]["history"] == [("My favourite colour is teal.", "Noted: My favourite colour is teal.")]
    assert next(chat for chat in history(client) if chat["id"] == old)["turns"] == 2
