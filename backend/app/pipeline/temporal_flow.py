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

    from app.pipeline import run_approvals, run_finish, run_resume, run_steps
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
    async def act(self, run: RunState) -> str:
        return run_finish.act_and_finish(self.lane, run, None)

    @activity.defn(name="resume_run")
    async def resume(self, envelope: Envelope) -> RunState | None:
        return run_resume.resume_run(self.lane, envelope.payload, envelope)

    @activity.defn(name="customer_wait_seconds")
    async def customer_wait_seconds(self) -> float:
        return run_finish.customer_wait(self.lane).total_seconds()

    @activity.defn(name="abandon_run")
    async def abandon(self, run_id: str) -> None:
        run_resume.abandon(self.lane, run_id)

    @activity.defn(name="close_without_acting")
    async def close(self, run: RunState) -> None:
        run_finish.close_without_acting(self.lane, run)

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
        self.messages: list[Envelope] = []  # later chat messages S4 joined to this run, for S6 to read
        self.deadline, self.round_seen = None, 0

    @workflow.run
    async def run(self, envelope: Envelope) -> str:
        # Step 1: S5, S6 and S7
        run = await step(RunActivities.start, envelope, timeout=REASON_TIMEOUT)

        # Step 2: act now, close, or wait for people (None: closed early, context unavailable, or joined to another run)
        outcome = await self.route(run) if run is not None else "done"

        # Step 3: while the agent waits for the customer's answer, a durable timer runs; their message takes the next turn
        while outcome == "awaiting_customer":
            outcome = await self.next_customer_turn(run.action.run_id)
        self.phase = "done"
        return self.phase

    async def route(self, run: RunState) -> str:
        """After S7: act (S9, S10), close, or wait for approvers (S8). Returns the outcome."""
        if run.verdict.route == "execute":
            return await step(RunActivities.act, run)
        if run.verdict.route != "approval_required":
            await step(RunActivities.close, run)
            return "closed"
        paused = await step(RunActivities.open_approval, run)
        while paused is not None:
            paused = await self.next_turn(paused)
        return "decided"

    async def next_customer_turn(self, run_id: str) -> str:
        """Wait for the customer, as long as the tenant allows. No answer: abandon. An answer: S5 to S7 again, then route."""
        wait = timedelta(seconds=await step(RunActivities.customer_wait_seconds))
        self.phase = "awaiting_customer"
        try:
            await workflow.wait_condition(lambda: bool(self.messages), timeout=wait)
        except asyncio.TimeoutError:
            await step(RunActivities.abandon, run_id)
            return "abandoned"
        self.phase = "running"
        resumed = await step(RunActivities.resume, self.messages.pop(0), timeout=REASON_TIMEOUT)
        return "awaiting_customer" if resumed is None else await self.route(resumed)

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

    @workflow.signal
    def add_message(self, envelope: Envelope) -> None:
        self.messages.append(envelope)

    @workflow.query
    def progress(self) -> dict:
        return {"phase": self.phase, "handled": self.handled, "messages": len(self.messages)}
