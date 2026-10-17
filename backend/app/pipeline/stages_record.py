# stages_record.py: S10 Record (a run to K10 and K11). S9 Act lives in stages_act.py.
# Used by: run_steps.py, tests. Uses: contracts_*.py, stages_decide.py (format_money).
from datetime import datetime

from app.pipeline.contracts_reason import ProposedAction
from app.pipeline.contracts_run import Cost, RunOutcome, RunRecord, RunStep, UiEvent
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.stages_decide import format_money

# Config: Sonnet price in US micro-dollars per token (USD 3 and 15 per million)
INPUT_USD_MICRO_PER_TOKEN = 3
OUTPUT_USD_MICRO_PER_TOKEN = 15


# --- S10 Record

def describe_cost(action: ProposedAction) -> Cost:
    """Token counts and their price, so Analytics can show cost per run."""
    usage = action.model
    usd_micro = usage.input_tokens * INPUT_USD_MICRO_PER_TOKEN + usage.output_tokens * OUTPUT_USD_MICRO_PER_TOKEN
    return Cost(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, usd_micro=usd_micro)


def describe_title(task: TaskRequest, action: ProposedAction | None) -> str:
    """'Issue refund LKR 12,000', or the activity when the run closed before proposing anything."""
    if action is None:
        return task.activity_id.removeprefix("act_").replace("_", " ").capitalize()
    amount = f" {format_money(action.money)}" if action.money else ""
    return f"{action.action_type.replace('_', ' ').capitalize()}{amount}"


def record(
    task: TaskRequest, action: ProposedAction | None, steps: list[RunStep], outcome: RunOutcome,
    approval_id: str | None, seed: dict, started_at: datetime, now: datetime, run_id: str | None = None,
) -> tuple[RunRecord, UiEvent]:
    """S10: close the run as K10 and tell the console as K11. The UI never sees personal data.
    action is None when the run closed early, for example when context was unavailable."""
    # Step 1: the run record S13 learns from
    run_id = action.run_id if action else run_id
    run = RunRecord(
        run_id=run_id, task_id=task.task_id, agent_id=task.agent_id, skill_ref=task.skill_ref,
        outcome=outcome, steps=steps, template_fills=[], human_touch=approval_id is not None,
        cost=describe_cost(action) if action else Cost(input_tokens=0, output_tokens=0, usd_micro=0),
        latency_ms=int((now - started_at).total_seconds() * 1000),
        trace_object_uri=f"s3://brain/{seed['tenant_id']}/traces/{run_id}.json",
    )

    # Step 2: one live event, about the approval when there is one
    event = UiEvent(
        type="approval.created" if approval_id else "run.updated", id=approval_id or run_id,
        tenant_id=seed["tenant_id"], cluster_id=seed["cluster_id"], env=seed["env"],
        display={"status": outcome, "title": describe_title(task, action)}, at=now,
    )
    return run, event
