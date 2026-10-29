# test_llm_cache.py: every Claude call marks its fixed parts for prompt caching, and keeps what changes per call after
# the last mark, so repeated calls read the cache instead of paying for the same tokens again.
# Uses: app/pipeline/llm.py.
from types import SimpleNamespace

from app.pipeline import llm

CACHE = {"type": "ephemeral"}


class FakeClient:
    """Records each request and answers with one text block."""

    def __init__(self, text: str = "PASS"):
        self.requests, self.text = [], text
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


def marked(blocks) -> bool:
    return isinstance(blocks, list) and blocks[-1].get("cache_control") == CACHE


def test_system_prompts_are_cached_on_every_kind_of_call():
    client = FakeClient("rule_a")
    llm.make_chooser(client)("refund please", {"rule_a": "refunds"})
    llm.make_grader(client)("rationale", ["doc"])
    llm.make_writer(client)("fix it", "hi there")
    llm.make_tool_caller(client)("act", [{"role": "user", "content": "go"}], [{"name": "t", "input_schema": {"type": "object"}}])
    assert all(marked(request["system"]) for request in client.requests)


def test_the_rules_are_cached_and_the_message_comes_after():
    client = FakeClient("rule_a")
    assert llm.make_chooser(client)("refund please", {"rule_a": "refunds"}) == "rule_a"
    rules, message = client.requests[0]["messages"][0]["content"]
    assert rules["cache_control"] == CACHE and "rule_a" in rules["text"]
    assert "cache_control" not in message and "refund please" in message["text"]


def test_a_tool_loop_caches_the_whole_request():
    client = FakeClient()
    llm.make_tool_caller(client)("act", [{"role": "user", "content": "go"}], [])
    assert client.requests[0]["cache_control"] == CACHE


def test_the_chat_so_far_is_cached_and_this_turns_documents_are_not():
    client = FakeClient("Thirty days. CITES: d1")
    text, cites = llm.make_answerer(client)("And for gifts?", [("d1", "Refunds: 30 days")], [("Refund window?", "Thirty days.")])
    assert (text, cites) == ("Thirty days.", ["d1"])
    *earlier, now = client.requests[0]["messages"]
    assert marked(earlier[-1]["content"]) and earlier[-1]["content"][0]["text"] == "Thirty days."
    assert isinstance(now["content"], str) and "Refunds: 30 days" in now["content"]


def test_a_first_question_has_no_history_to_mark():
    client = FakeClient("Hi. CITES: none")
    llm.make_answerer(client)("hi", [])
    assert len(client.requests[0]["messages"]) == 1


def test_the_word_list_is_cached_before_the_transcript():
    client = FakeClient("Go to the audit trail")
    llm.make_writer(client)("fix it", "<transcript>order trail</transcript>", "Word list: Audit trail")
    words, transcript = client.requests[0]["messages"][0]["content"]
    assert words["cache_control"] == CACHE and "cache_control" not in transcript
