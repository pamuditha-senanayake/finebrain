# test_small_talk.py: "hi", "thanks" and "bye" get a quick reply with no search and no model call, with Claude on or
# off, and the turn is remembered so the next real question sees it. A message with a real question still goes to Claude.
# Uses: app/api/small_talk.py, ask.py, tests/test_api_brain.py (helpers).
import pytest

from app.api import small_talk
from tests.test_api_brain import QUESTION, Recorder, build, post_ask


@pytest.mark.parametrize("said, starts", [
    ("Hi", "Hi sir."), ("hello there!", "Hi sir."), ("Hey Lisena", "Hi sir."), ("Good morning", "Hi sir."),
    ("hi, how are you?", "I am well"), ("How's it going", "I am well"),
    ("Thanks!", "You are welcome"), ("ok thank you so much", "You are welcome"),
    ("bye", "Goodbye"), ("See you later", "Goodbye"),
])
def test_small_talk_is_recognised(said, starts):
    assert small_talk.reply(said, "sir").startswith(starts)


@pytest.mark.parametrize("said", ["hi, what is our refund window?", "thanks, now show me the policy", "who are you", "", "hit the target"])
def test_a_real_question_is_not_small_talk(said):
    assert small_talk.reply(said, "sir") is None


@pytest.mark.parametrize("answerer", [None, "recorder"])
def test_hi_is_answered_at_once_with_claude_on_or_off(answerer):
    recorder = Recorder()
    client, _ = build(answerer=recorder if answerer else None)
    body = post_ask(client, "Hi").json()
    assert body["answer"].startswith("Hi ") and body["citations"] == [] and "documents" not in body["answer"]
    assert recorder.calls == []  # no model call for a greeting


def test_the_greeting_is_remembered_for_the_next_question():
    recorder = Recorder()
    client, _ = build(answerer=recorder)
    first = post_ask(client, "hello").json()
    post_ask(client, QUESTION, conversation=first["conversationId"])
    assert recorder.calls[0]["history"][0][0] == "hello" and recorder.calls[0]["question"] == QUESTION
