# temporal_flow.py: S4 on Temporal. Each task is a durable workflow; S8 waits for an approval signal.
# Used by: temporal_runner.py, adapters.py (temporal_is_up). Uses: run_steps.py.
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():  # these never run inside the workflow sandbox
    import asyncio
    import os

    from temporalio.client import Client

    from app.pipeline import run_steps
    from app.pipeline.contracts_signal import Envelope
    from app.pipeline.run_steps import RunState

# Config
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
STEP_TIMEOUT = timedelta(seconds=30)
REASON_TIMEOUT = timedelta(seconds=240)  # S5 + S6 + S7: Claude with up to 3 tries and 2 feedback rounds
NO_AUTO_RETRY = RetryPolicy(maximum_attempts=1)  # steps publish messages; retrying here could publish twice


def temporal_is_up(address: str = TEMPORAL_ADDRESS) -> bool:
    """True when the Temporal server answers, so tests can skip cleanly when Docker is down."""
    try:
        asyncio.run(asyncio.wait_for(Client.connect(address), timeout=3))
    except Exception:
        return False
    return True


# --- Activities: the S4 run steps, with the lane they act on

class RunActivities:
    """A class because every activity needs the same lane: bus, stores, model and gateway."""

    def __init__(self, lane):
        self.lane = lane

    @activity.defn(name="start_run")
    async def start(self, envelope: Envelope) -> RunState | None:
        return run_steps.start_run(self.lane, envelope)

    @activity.defn(name="act_and_finish")
    async def act(self, run: RunState) -> None:
        run_steps.act_and_finish(self.lane, run, None)

    @activity.defn(name="close_without_acting")
    async def close(self, run: RunState) -> None:
        run_steps.close_without_acting(self.lane, run)

    @activity.defn(name="open_approval")
    async def open_approval(self, run: RunState) -> RunState:
        return run_steps.open_approval(self.lane, run)

    @activity.defn(name="resume_after_decision")
    async def resume(self, run: RunState, envelope: Envelope) -> None:
        run_steps.resume_after_decision(self.lane, run, envelope)


# --- Workflow: one per task

@workflow.defn
class TaskWorkflow:
    def __init__(self) -> None:
        self.phase = "running"
        self.decision: Envelope | None = None

    @workflow.run
    async def run(self, envelope: Envelope) -> str:
        # Step 1: S5, S6 and S7
        run = await workflow.execute_activity_method(RunActivities.start, envelope, start_to_close_timeout=REASON_TIMEOUT, retry_policy=NO_AUTO_RETRY)

        # Step 2: act now, close, or wait for a human (None: closed early, context unavailable)
        if run is None:
            pass
        elif run.verdict.route == "execute":
            await workflow.execute_activity_method(RunActivities.act, run, start_to_close_timeout=STEP_TIMEOUT, retry_policy=NO_AUTO_RETRY)
        elif run.verdict.route != "approval_required":
            await workflow.execute_activity_method(RunActivities.close, run, start_to_close_timeout=STEP_TIMEOUT, retry_policy=NO_AUTO_RETRY)
        else:
            await self.wait_for_human(run)
        self.phase = "done"
        return self.phase

    async def wait_for_human(self, run: RunState) -> None:
        """S8: open the approval, then sleep durably until the decision signal arrives."""
        paused = await workflow.execute_activity_method(RunActivities.open_approval, run, start_to_close_timeout=STEP_TIMEOUT, retry_policy=NO_AUTO_RETRY)
        self.phase = "awaiting_approval"
        await workflow.wait_condition(lambda: self.decision is not None)
        self.phase = "running"
        await workflow.execute_activity_method(RunActivities.resume, args=[paused, self.decision], start_to_close_timeout=STEP_TIMEOUT, retry_policy=NO_AUTO_RETRY)

    @workflow.signal
    def decide(self, envelope: Envelope) -> None:
        self.decision = envelope

    @workflow.query
    def current_phase(self) -> str:
        return self.phase
