# stages_record.py: S9 Act (cleared K5 to K9) and S10 Record (run to K10 and K11).
# Used by: tests/test_stages.py. Uses: contracts_*.py, stages_govern.py (format_money), fakes.py (Gateway type).
import hashlib
import json
from datetime import datetime

from app.pipeline.contracts_reason import ProposedAction
from app.pipeline.contracts_run import (
    ActionError, ActionResult, Cost, Decision, GovernanceVerdict, RunOutcome, RunRecord, RunStep, UiEvent,
)
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.fakes import Gateway
from app.pipeline.stages_govern import format_money

# Config: Sonnet price in US micro-dollars per token (USD 3 and 15 per million)
INPUT_USD_MICRO_PER_TOKEN = 3
OUTPUT_USD_MICRO_PER_TOKEN = 15


class NotCleared(Exception):
    """S9 was asked to act on something governance did not clear."""


# --- S9 Act

def is_cleared(verdict: GovernanceVerdict, decision: Decision | None) -> bool:
    """Nothing acts before governance: either the route is execute, or a human approved."""
    if verdict.route == "execute":
        return True
    return decision is not None and decision.decision == "approve"


def act(
    action: ProposedAction, verdict: GovernanceVerdict, decision: Decision | None,
    tenant_id: str, gateway: Gateway, new_id, now: datetime,
) -> ActionResult:
    """S9: call the tool with a stable idempotency key, so a retry can never pay twice."""
    # Step 1: refuse anything governance did not clear
    if not is_cleared(verdict, decision):
        raise NotCleared(f"{action.run_id}:{action.step_id} route is {verdict.route}")

    # Step 2: a human edit wins over the agent's arguments
    arguments = decision.final_arguments if decision and decision.final_arguments else action.arguments
    key = f"{tenant_id}:{action.run_id}:{action.step_id}"
    response = gateway(action.tool_id, arguments, key)

    # Step 3: describe the result as K9
    error = response.get("error")
    return ActionResult(
        action_id=new_id("actn"), run_id=action.run_id, tool_id=action.tool_id, idempotency_key=key,
        status=response["status"], external_ref=response.get("external_ref"),
        request_hash=hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest(),
        response_summary=response.get("summary", ""), attempted_at=now,
        completed_at=now if response["status"] == "succeeded" else None,
        error=ActionError(**error) if error else None,
    )


# --- S10 Record

def describe_cost(action: ProposedAction) -> Cost:
    """Token counts and their price, so Analytics can show cost per run."""
    usage = action.model
    usd_micro = usage.input_tokens * INPUT_USD_MICRO_PER_TOKEN + usage.output_tokens * OUTPUT_USD_MICRO_PER_TOKEN
    return Cost(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, usd_micro=usd_micro)


def record(
    task: TaskRequest, action: ProposedAction, steps: list[RunStep], outcome: RunOutcome,
    approval_id: str | None, seed: dict, started_at: datetime, now: datetime,
) -> tuple[RunRecord, UiEvent]:
    """S10: close the run as K10 and tell the console as K11. The UI never sees personal data."""
    # Step 1: the run record S13 learns from
    run = RunRecord(
        run_id=action.run_id, task_id=task.task_id, agent_id=task.agent_id, skill_ref=task.skill_ref,
        outcome=outcome, steps=steps, template_fills=[], human_touch=approval_id is not None,
        cost=describe_cost(action), latency_ms=int((now - started_at).total_seconds() * 1000),
        trace_object_uri=f"s3://brain/{seed['tenant_id']}/traces/{action.run_id}.json",
    )

    # Step 2: one live event, about the approval when there is one
    title = f"{action.action_type.replace('_', ' ').capitalize()} {format_money(action.money)}"
    event = UiEvent(
        type="approval.created" if approval_id else "run.updated", id=approval_id or action.run_id,
        tenant_id=seed["tenant_id"], cluster_id=seed["cluster_id"], env=seed["env"],
        display={"status": outcome, "title": title}, at=now,
    )
    return run, event
