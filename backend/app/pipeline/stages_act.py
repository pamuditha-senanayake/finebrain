# stages_act.py: S9 Act (a cleared K5 to K9). Runs the tool once per idempotency key: rate limited, retried with
# the same key on retryable errors, and remembered so a retry after a crash never calls the tool again.
# Used by: run_steps.py, run_approvals.py (policy_is_stale), tests. Uses: tool_runners.py, retry.py, observe.py, contracts_run.py.
import hashlib
import json
from datetime import datetime

from app.pipeline.contracts_reason import ProposedAction
from app.pipeline.contracts_run import ActionError, ActionResult, Decision, GovernanceVerdict
from app.pipeline.observe import count, log_event
from app.pipeline.retry import call_with_retry
from app.pipeline.tool_runners import RateLimited, ToolFailed, run_tool
from app.pipeline.tools import TOOLS

# Config
ATTEMPTS = 6  # reference doc section 8 (K9): retryable tool errors get up to 6 attempts, same idempotency key
COMPENSATIONS: dict[str, str] = {}  # tool_id -> what undoes it; no Lane A tool needs one yet


class NotCleared(Exception):
    """S9 was asked to act on something governance did not clear."""


def is_cleared(verdict: GovernanceVerdict, decision: Decision | None) -> bool:
    """Nothing acts before governance: either the route is execute, or a human approved."""
    if verdict.route == "execute":
        return True
    return decision is not None and decision.decision == "approve"


def policy_is_stale(verdict: GovernanceVerdict, policies: dict) -> bool:
    """True when a policy S7 judged against has a newer release now (K14: check the commit on every run)."""
    return any(
        (current := policies.get(result.policy_ref.id)) is not None and current["_ref"]["version"] != result.policy_ref.version
        for result in verdict.policy_results
    )


def call_once(action: ProposedAction, arguments: dict, key: str, tenant_id: str, tooling: dict, now: datetime) -> dict:
    """One attempt: within the rate limit, through the tool's runner."""
    if not tooling["limiter"].allow(tenant_id, action.tool_id, TOOLS[action.action_type]["rate_per_minute"], now):
        raise RateLimited(f"{action.tool_id} limit reached")
    return run_tool(action.action_type, action.tool_id, arguments, key, tooling["runners"])


def describe(action: ProposedAction, arguments: dict, key: str, response: dict | None, error: Exception | None, new_id, now: datetime) -> ActionResult:
    """K9 for a success or a failure. The summary never holds personal data."""
    failed = error is not None
    code = getattr(error, "code", type(error).__name__) if failed else None
    return ActionResult(
        action_id=new_id("actn"), run_id=action.run_id, tool_id=action.tool_id, idempotency_key=key,
        status="failed" if failed else "succeeded", external_ref=None if failed else response.get("external_ref"),
        request_hash=hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest(),
        response_summary=f"failed: {code}; compensation: {COMPENSATIONS.get(action.tool_id, 'none defined')}" if failed else response.get("summary", ""),
        attempted_at=now, completed_at=None if failed else now,
        error=ActionError(code=code, retryable=bool(getattr(error, "retryable", False))) if failed else None,
    )


def act(action: ProposedAction, verdict: GovernanceVerdict, decision: Decision | None, tenant_id: str, tooling: dict, new_id, now: datetime) -> ActionResult:
    """S9: act once. A stored result is returned as is; retryable errors are retried; failures come back as K9."""
    # Step 1: refuse anything governance did not clear; a human edit wins over the agent's arguments
    if not is_cleared(verdict, decision):
        raise NotCleared(f"{action.run_id}:{action.step_id} route is {verdict.route}")
    arguments = decision.final_arguments if decision and decision.final_arguments else action.arguments
    key = f"{tenant_id}:{action.run_id}:{action.step_id}"

    # Step 2: already done (for example, a crash after paying)? Then never call the tool again
    stored = tooling["results"].get(key)
    if stored is not None:
        count("s9.replayed")
        return ActionResult.model_validate(stored)

    # Step 3: call with retries on the same key, then remember a success
    try:
        response = call_with_retry(lambda: call_once(action, arguments, key, tenant_id, tooling, now), lambda error: getattr(error, "retryable", False), attempts=ATTEMPTS, sleep=tooling["sleep"])
    except (ToolFailed, RateLimited) as error:
        count(f"s9.failed.{getattr(error, 'code', 'rate_limited')}")
        log_event("S9", "failed", run_id=action.run_id, tool_id=action.tool_id, error=str(error))
        return describe(action, arguments, key, None, error, new_id, now)
    result = describe(action, arguments, key, response, None, new_id, now)
    tooling["results"].put(key, result.model_dump(mode="json"))
    return result
