# fakes.py: in-memory stand-ins for outside services, so stage tests are fast and repeatable.
# Used by: tests and demos, which pass them into stages_*.py and orchestrate.py.
# Uses: nothing local. Object store, PII vault and dedup set need no fake: a plain dict or set is enough.
import hashlib
import itertools
import json
import math
import re
from collections.abc import Callable
from types import SimpleNamespace

Model = Callable[[str, list, list], object]  # call(system, messages, tools) -> a Claude reply
Gateway = Callable[[str, dict, str], dict]


# --- Ids

def make_id_maker() -> Callable[[str], str]:
    """Return new_id(prefix) giving prefix_0001, prefix_0002, ... so ids match on every run."""
    counters: dict[str, itertools.count] = {}

    def new_id(prefix: str) -> str:
        counter = counters.setdefault(prefix, itertools.count(1))
        return f"{prefix}_{next(counter):04d}"

    return new_id


# --- Claude (Anthropic in production)

def tool_response(tool: str, tool_input: dict, model: str = "claude-sonnet-5-5", input_tokens: int = 0, output_tokens: int = 0):
    """A reply shaped like the Claude API's, holding one tool call."""
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(model=model, stop_reason="tool_use", usage=usage, content=[SimpleNamespace(type="tool_use", id="toolu_fake", name=tool, input=tool_input)])


def text_response(text: str):
    """A reply with no tool call, like a refusal."""
    usage = SimpleNamespace(input_tokens=0, output_tokens=0)
    return SimpleNamespace(model="claude-sonnet-5-5", stop_reason="end_turn", usage=usage, content=[SimpleNamespace(type="text", text=text)])


def make_recorded_caller(answers: dict[str, dict]):
    """A Claude stand-in for S6: answers with the recorded tool call whose payment ref appears in the request.
    Returns the caller and the list of requests it saw."""
    calls: list[dict] = []

    def call(system: str, messages: list[dict], tools: list[dict]):
        calls.append({"system": system, "messages": messages, "tools": tools})
        text = json.dumps(messages)
        answer = next((answer for ref, answer in answers.items() if ref in text), None)
        return tool_response(**answer) if answer else text_response("I cannot help with that.")

    return call, calls


def pass_grader(rationale: str, documents: list[str], context: str = "") -> tuple[bool, str]:
    """An S7 grader stand-in that passes anything with at least one cited document."""
    return bool(documents), "fake grader" if documents else "no documents cited"


# --- Payment gateway

def make_fake_gateway(fail_with: str | None = None, failures: int | None = None, retryable: bool = True) -> tuple[Gateway, dict[str, dict]]:
    """A refund gateway that answers once per idempotency key, like a real one.
    fail_with makes it fail: every call, or only the first `failures` calls."""
    seen: dict[str, dict] = {}
    calls = {"count": 0}

    def gateway(tool_id: str, arguments: dict, idempotency_key: str) -> dict:
        calls["count"] += 1
        if fail_with and (failures is None or calls["count"] <= failures):
            return {"status": "failed", "error": {"code": fail_with, "retryable": retryable}}
        if idempotency_key not in seen:
            external_ref = "rf_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:8]
            seen[idempotency_key] = {"status": "succeeded", "external_ref": external_ref, "summary": f"{tool_id} accepted", "arguments": arguments}
        return seen[idempotency_key]

    return gateway, seen


def make_fake_sender() -> tuple[Gateway, list[dict]]:
    """An email sender stand-in for reply_customer: records what would be sent."""
    sent: list[dict] = []

    def send(tool_id: str, arguments: dict, idempotency_key: str) -> dict:
        sent.append({"key": idempotency_key, **arguments})
        return {"status": "succeeded", "external_ref": f"msg_{len(sent):04d}", "summary": "reply sent"}

    return send, sent


# --- Embeddings and rerank (Voyage in production)

EMBEDDING_SIZE = 1024


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def fake_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Hashed bag of words: texts sharing words get similar vectors, and the same text always gets the same one."""
    vectors = []
    for text in texts:
        vector = [0.0] * EMBEDDING_SIZE
        for word in words(text):
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBEDDING_SIZE] += 1.0
        length = math.sqrt(sum(value * value for value in vector)) or 1.0
        vectors.append([value / length for value in vector])
    return vectors


def fake_rerank(query: str, documents: list[str]) -> list[float]:
    """Share of the query's words found in each document."""
    asked = set(words(query)) or {""}
    return [len(asked & set(words(document))) / len(asked) for document in documents]
