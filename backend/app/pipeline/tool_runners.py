# tool_runners.py: what S9 needs to run a tool safely: a runner per tool, a rate limiter, and a store of finished
# results keyed by idempotency key. Memory and Valkey versions. Used by: stages_act.py, adapters.py, tests.
# Uses: tools.py. Runners are callables (tool_id, arguments, idempotency_key) -> {status, external_ref, summary, error}.
import json
from datetime import datetime

from app.pipeline.tools import TOOLS

# Config
RESULT_TTL_SECONDS = 7 * 24 * 3600  # reference doc section 7: idempotency keys live up to 7 days
RATE_WINDOW_SECONDS = 60
HANDED_TO_HUMAN = {"status": "succeeded", "external_ref": None, "summary": "handed to a human"}


class RateLimited(Exception):
    """This tool's per-minute limit for the tenant is used up. Waiting helps, so it is retryable."""
    retryable = True


class ToolFailed(Exception):
    """The outside system said no. retryable comes from its error code."""

    def __init__(self, code: str, retryable: bool):
        super().__init__(code)
        self.code, self.retryable = code, retryable


# --- Running one tool

def run_tool(action_type: str, tool_id: str, arguments: dict, key: str, runners: dict) -> dict:
    """Send the call to the tool's runner. Escalate has no outside call."""
    runner = TOOLS[action_type]["runner"]
    if runner == "none":
        return HANDED_TO_HUMAN
    response = runners[runner](tool_id, arguments, key)
    if response["status"] == "failed":
        error = response.get("error") or {"code": "unknown_error", "retryable": False}
        raise ToolFailed(error["code"], error["retryable"])
    return response


# --- Rate limits: a counter per tenant, tool and minute

def window_key(tenant_id: str, tool_id: str, now: datetime) -> str:
    return f"{tenant_id}:rate:{tool_id}:{int(now.timestamp()) // RATE_WINDOW_SECONDS}"


class MemoryRateLimiter:
    def __init__(self):
        self.counts: dict[str, int] = {}

    def allow(self, tenant_id: str, tool_id: str, limit: int | None, now: datetime) -> bool:
        if limit is None:
            return True
        key = window_key(tenant_id, tool_id, now)
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key] <= limit


class ValkeyRateLimiter:
    """INCR plus an expiry: one atomic count per window, shared by every worker."""

    def __init__(self, client):
        self.client = client

    def allow(self, tenant_id: str, tool_id: str, limit: int | None, now: datetime) -> bool:
        if limit is None:
            return True
        key = window_key(tenant_id, tool_id, now)
        used = self.client.incr(key)
        self.client.expire(key, RATE_WINDOW_SECONDS * 2)
        return used <= limit


# --- Finished results, so a retry after a crash never calls the tool again

class MemoryResults:
    def __init__(self):
        self.results: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self.results.get(key)

    def put(self, key: str, result: dict) -> None:
        self.results.setdefault(key, result)


class ValkeyResults:
    def __init__(self, client, namespace: str):
        self.client, self.namespace = client, namespace

    def get(self, key: str) -> dict | None:
        stored = self.client.get(f"{self.namespace}:{key}")
        return json.loads(stored) if stored else None

    def put(self, key: str, result: dict) -> None:
        self.client.set(f"{self.namespace}:{key}", json.dumps(result), ex=RESULT_TTL_SECONDS, nx=True)
