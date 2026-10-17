# fakes.py: in-memory stand-ins for outside services, so stage tests are fast and repeatable.
# Used by: tests/test_stages.py, tests/test_chain.py, which pass them into stages_*.py and orchestrate.py.
# Uses: nothing local. Object store, PII vault and dedup set need no fake: a plain dict or set is enough.
import hashlib
import itertools
import json
from collections.abc import Callable

Model = Callable[[str, dict], dict]
Gateway = Callable[[str, dict, str], dict]


# --- Ids

def make_id_maker() -> Callable[[str], str]:
    """Return new_id(prefix) giving prefix_0001, prefix_0002, ... so ids match on every run."""
    counters: dict[str, itertools.count] = {}

    def new_id(prefix: str) -> str:
        counter = counters.setdefault(prefix, itertools.count(1))
        return f"{prefix}_{next(counter):04d}"

    return new_id


# --- Model (Anthropic in production)

def make_recorded_model(answer: dict) -> tuple[Model, list[tuple[str, dict]]]:
    """A model that always gives the recorded answer, plus the list of calls it saw."""
    calls: list[tuple[str, dict]] = []

    def model(prompt_name: str, context: dict) -> dict:
        calls.append((prompt_name, context))
        return answer

    return model, calls


def make_model_by_ref(answers: dict[str, dict]) -> Model:
    """One model for many runs: it gives the answer whose payment ref appears in the context."""

    def model(prompt_name: str, context: dict) -> dict:
        text = json.dumps(context)
        return next(answer for ref, answer in answers.items() if ref in text)

    return model


# --- Payment gateway

def make_fake_gateway(fail_with: str | None = None) -> tuple[Gateway, dict[str, dict]]:
    """A refund gateway that answers once per idempotency key, like a real one."""
    seen: dict[str, dict] = {}

    def gateway(tool_id: str, arguments: dict, idempotency_key: str) -> dict:
        if fail_with:
            return {"status": "failed", "error": {"code": fail_with, "retryable": True}}
        if idempotency_key not in seen:
            external_ref = "rf_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:8]
            seen[idempotency_key] = {"status": "succeeded", "external_ref": external_ref, "summary": f"{tool_id} accepted"}
        return seen[idempotency_key]

    return gateway, seen
