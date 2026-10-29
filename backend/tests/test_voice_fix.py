# test_voice_fix.py: a spoken question is corrected against the company's own words before it is asked. Claude off, a
# failed call, or a "fix" that is really an answer all keep the words as heard, so voice never stops over it.
# Uses: app/api/voice_fix.py, routes.py, tests/test_api_brain.py (helpers).
from fastapi.testclient import TestClient

from app.api import voice_fix
from app.api.routes import create_api_app
from app.pipeline import fakes, orchestrate
from tests.golden import NOW, recorded_answers
from tests.test_api_brain import FOUNDER, HQ, SEED, TENANT


class Writer:
    """Answers with a fixed reply and keeps the prompts, so tests can see the word list."""

    def __init__(self, reply: str | Exception):
        self.reply, self.prompts = reply, []

    def __call__(self, system: str, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def post_fix(writer, text: str, persona: str = FOUNDER, pages: list[str] | None = None):
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    client = TestClient(create_api_app(lane, HQ, None, None, writer))
    return client.post(f"/api/t/{TENANT}/voice/fix", json={"text": text, "pages": pages or ["Audit trail"], "recent": ["What is our refund window?"]}, headers={"x-persona": persona})


def test_misheard_words_are_fixed_with_the_company_words_and_pages():
    writer = Writer("Go to the audit trail")
    body = post_fix(writer, "go to the order trail").json()
    assert body == {"text": "Go to the audit trail", "changed": True}
    assert "Audit trail" in writer.prompts[0] and "Lisena" in writer.prompts[0] and "Pamuditha" in writer.prompts[0]
    assert "What is our refund window?" in writer.prompts[0]  # the chat so far helps pick the right word


def test_claude_off_or_failing_keeps_the_words_as_heard():
    assert post_fix(None, "go to the order trail").json() == {"text": "go to the order trail", "changed": False}
    assert post_fix(Writer(TimeoutError()), "go to the order trail").json()["text"] == "go to the order trail"
    assert post_fix(Writer(""), "hello").json()["text"] == "hello"


def test_an_answer_instead_of_a_fix_is_dropped():
    long_reply = "The refund window is thirty days for every customer, as the policy says, and approvals take a day."
    assert post_fix(Writer(long_reply), "refund window").json()["text"] == "refund window"


def test_bad_requests():
    assert post_fix(Writer("x"), "  ").status_code == 400
    assert post_fix(Writer("x"), "hi", persona="h-stranger").status_code == 401


def test_company_words_name_people_teams_and_the_tenant():
    words = voice_fix.company_words(SEED, HQ)
    assert HQ["tenant"]["name"] in words and "Pamuditha" in words and "Lisena" in words
    assert len(words) == len(set(words))
