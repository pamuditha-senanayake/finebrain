# stages_record.py: S10 Record (a run to K10 and K11): the run record, its trace in S3, and the live UI event,
# with a last check that no personal data slipped into what people see. S9 Act lives in stages_act.py.
# Used by: run_steps.py, tests. Uses: contracts_*.py, stages_decide.py (format_money), pii.py, retry.py, observe.py.
import json
from datetime import datetime

from app.pipeline import pii
from app.pipeline.observe import count, log_event
from app.pipeline.retry import call_with_retry

from app.pipeline.contracts_reason import ProposedAction
from app.pipeline.contracts_run import Cost, RunOutcome, RunRecord, RunStep, UiEvent
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.stages_decide import format_money

# Config: Sonnet price in US micro-dollars per token (USD 3 and 15 per million)
INPUT_USD_MICRO_PER_TOKEN = 3
OUTPUT_USD_MICRO_PER_TOKEN = 15
TRACE_ATTEMPTS = 3
LEAK_PATTERNS = [pii.EMAIL_PATTERN, pii.NIC_PATTERN, pii.PHONE_PATTERN]
MASKED = "[masked]"


# --- Traces and the personal-data guard

def trace_uri(seed: dict, run_id: str) -> str:
    return f"s3://brain/{seed['tenant_id']}/traces/{run_id}.json"


def write_trace(object_store, uri: str, trace: dict) -> bool:
    """Write the full trace, retrying briefly. False when the store stays down: the run record goes out anyway."""
    try:
        call_with_retry(lambda: object_store.__setitem__(uri, json.dumps(trace, default=str).encode()), lambda error: True, attempts=TRACE_ATTEMPTS, base_delay=0.1)
    except Exception as error:
        count("s10.trace_failed")
        log_event("S10", "trace_failed", uri=uri, error=type(error).__name__)
        return False
    return True


def mask_leaks(text: str) -> str:
    """Second line of defense after S2: anything that looks personal is masked before people see it."""
    leaks = [match for pattern in LEAK_PATTERNS for match in pattern.findall(text)] + pii.find_cards(text)
    for leak in leaks:
        text = text.replace(leak, MASKED)
    if leaks:
        count("s10.pii_masked", len(leaks))
    return text


def guard_display(display: dict) -> dict:
    return {key: mask_leaks(value) if isinstance(value, str) else value for key, value in display.items()}


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
    approval_id: str | None, seed: dict, started_at: datetime, now: datetime, run_id: str | None = None, trace_written: bool = True,
    decided_by: str | None = None,
) -> tuple[RunRecord, UiEvent]:
    """S10: close the run as K10 and tell the console as K11. The UI never sees personal data.
    action is None when the run closed early, for example when context was unavailable."""
    # Step 1: the run record S13 learns from
    run_id = action.run_id if action else run_id
    run = RunRecord(
        run_id=run_id, task_id=task.task_id, agent_id=task.agent_id, skill_ref=task.skill_ref,
        outcome=outcome, steps=[step.model_copy(update={"reason": mask_leaks(step.reason)}) for step in steps],
        template_fills=[], human_touch=approval_id is not None,
        cost=describe_cost(action) if action else Cost(input_tokens=0, output_tokens=0, usd_micro=0),
        latency_ms=int((now - started_at).total_seconds() * 1000),
        trace_object_uri=trace_uri(seed, run_id) if trace_written else "pending:" + trace_uri(seed, run_id), decided_by=decided_by,
    )

    # Step 2: one live event, about the approval when there is one
    event = UiEvent(
        type="approval.created" if approval_id else "run.updated", id=approval_id or run_id,
        tenant_id=seed["tenant_id"], cluster_id=seed["cluster_id"], env=seed["env"],
        display=guard_display({"status": outcome, "title": describe_title(task, action)}), at=now,
    )
    return run, event
