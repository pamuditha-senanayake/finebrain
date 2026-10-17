# temporal_flow.py: S4 on Temporal. Each task is a durable workflow. S8 waits for decision signals with a timer
# for expiry, hands to the delegate once, and sleeps through a C4 cooling period before acting.
# Used by: temporal_runner.py, adapters.py (temporal_is_up). Uses: run_steps.py, run_approvals.py.
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():  # these never run inside the workflow sandbox
    import asyncio
    import concurrent.futures
    import os

    from temporalio.client import Client

    from app.pipeline import run_approvals, run_steps
    from app.pipeline.contracts_signal import Envelope
    from app.pipeline.run_steps import RunState

# Config
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
STEP_TIMEOUT = timedelta(seconds=30)
REASON_TIMEOUT = timedelta(seconds=240)  # S5 + S6 + S7: Claude with up to 3 tries and 2 feedback rounds
NO_AUTO_RETRY = RetryPolicy(maximum_attempts=1)  # steps publish messages; retrying here could publish twice


def temporal_is_up(address: str = TEMPORAL_ADDRESS) -> bool:
    """True when the Temporal server answers. Runs on its own thread, so it also works inside a running event loop (the API)."""
    def probe() -> None:
        asyncio.run(asyncio.wait_for(Client.connect(address), timeout=3))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(probe).result(timeout=5)
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
        return run_approvals.open_approval(self.lane, run)

    @activity.defn(name="handle_decision")
    async def handle_decision(self, run: RunState, envelope: Envelope) -> RunState | None:
        return run_approvals.handle_decision(self.lane, run, envelope)

    @activity.defn(name="expire_approval")
    async def expire(self, run: RunState) -> RunState | None:
        return run_approvals.expire(self.lane, run)

    @activity.defn(name="release_after_cooling")
    async def release(self, run: RunState) -> RunState | None:
        return run_approvals.release(self.lane, run)


async def step(method, *args, timeout: timedelta = STEP_TIMEOUT):
    return await workflow.execute_activity_method(method, args=list(args), start_to_close_timeout=timeout, retry_policy=NO_AUTO_RETRY)


# --- Workflow: one per task

@workflow.defn
class TaskWorkflow:
    def __init__(self) -> None:
        self.phase, self.handled = "running", 0
        self.inbox: list[Envelope] = []
        self.deadline, self.round_seen = None, 0

    @workflow.run
    async def run(self, envelope: Envelope) -> str:
        # Step 1: S5, S6 and S7
        run = await step(RunActivities.start, envelope, timeout=REASON_TIMEOUT)

        # Step 2: act now, close, or wait for people (None: closed early, context unavailable)
        if run is not None and run.verdict.route == "execute":
            await step(RunActivities.act, run)
        elif run is not None and run.verdict.route != "approval_required":
            await step(RunActivities.close, run)
        elif run is not None:
            paused = await step(RunActivities.open_approval, run)
            while paused is not None:
                paused = await self.next_turn(paused)
        self.phase = "done"
        return self.phase

    async def next_turn(self, paused: RunState) -> RunState | None:
        """One turn of S8: sleep through cooling and act, or wait for a decision until the round's deadline."""
        state = paused.approval
        if state.final_decision is not None:
            self.phase = "cooling"
            await asyncio.sleep(state.cooling_seconds)  # a durable Temporal timer
            return await step(RunActivities.release, paused)  # a new approval if the policy changed meanwhile
        if state.round != self.round_seen:  # each round (first approver, then delegate) gets its own clock
            self.deadline, self.round_seen = workflow.now() + timedelta(seconds=state.expires_after_seconds), state.round
        self.phase = "awaiting_approval"
        try:
            await workflow.wait_condition(lambda: bool(self.inbox), timeout=max(self.deadline - workflow.now(), timedelta(0)))
        except asyncio.TimeoutError:
            self.phase = "running"
            return await step(RunActivities.expire, paused)
        self.phase = "running"
        result = await step(RunActivities.handle_decision, paused, self.inbox.pop(0), timeout=REASON_TIMEOUT)
        self.handled += 1
        return result

    @workflow.signal
    def decide(self, envelope: Envelope) -> None:
        self.inbox.append(envelope)

    @workflow.query
    def progress(self) -> dict:
        return {"phase": self.phase, "handled": self.handled}
