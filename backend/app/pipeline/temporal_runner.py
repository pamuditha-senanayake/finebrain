# temporal_runner.py: lets the sync bus handlers drive async Temporal: a worker per lane, start, signal, wait.
# Used by: adapters.py, orchestrate.py (start_task, send_decision, stop). Uses: temporal_flow.py.
import asyncio
import threading
import time

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from app.pipeline.contracts_signal import Envelope
from app.pipeline.temporal_flow import TEMPORAL_ADDRESS, RunActivities, TaskWorkflow

# Config
WAIT_SECONDS = 30
AT_REST = {"awaiting_approval", "done"}


class TemporalRunner:
    """A class because the event loop thread, client and worker start and stop together."""

    def __init__(self, address: str = TEMPORAL_ADDRESS):
        self.address = address

    def start(self, lane) -> None:
        """Run a worker for this lane on its own task queue, in a background event loop."""
        self.lane = lane
        self.task_queue = f"lane-a-{lane.seed['tenant_id']}"  # one queue per lane, so lanes never share work
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.client = self.call(Client.connect(self.address, data_converter=pydantic_data_converter))
        self.worker = self.call(self.make_worker(RunActivities(lane)))
        asyncio.run_coroutine_threadsafe(self.worker.run(), self.loop)

    async def make_worker(self, activities: RunActivities) -> Worker:
        return Worker(
            self.client, task_queue=self.task_queue, workflows=[TaskWorkflow],
            activities=[activities.start, activities.act, activities.close, activities.open_approval, activities.resume],
        )

    def call(self, coroutine):
        """Run one coroutine on the background loop and wait for its result."""
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(WAIT_SECONDS)

    def workflow_id(self, task_id: str) -> str:
        return f"{self.lane.seed['tenant_id']}:{task_id}"

    def start_task(self, envelope: Envelope) -> None:
        """Start the task's workflow and wait until it acts, closes, or pauses for a human."""
        task_id = envelope.payload["task_id"]
        self.call(self.client.start_workflow(TaskWorkflow.run, envelope, id=self.workflow_id(task_id), task_queue=self.task_queue))
        self.wait_for_phase(task_id, AT_REST)

    def send_decision(self, task_id: str, envelope: Envelope) -> None:
        """Signal the paused workflow and wait until it finishes."""
        self.call(self.client.get_workflow_handle(self.workflow_id(task_id)).signal(TaskWorkflow.decide, envelope))
        self.wait_for_phase(task_id, {"done"})

    def wait_for_phase(self, task_id: str, wanted: set[str]) -> None:
        """The bus handler waits, so the next message it reads sees everything this run published."""
        handle = self.client.get_workflow_handle(self.workflow_id(task_id))
        deadline = time.monotonic() + WAIT_SECONDS
        while self.call(handle.query(TaskWorkflow.current_phase)) not in wanted:
            if time.monotonic() > deadline:
                raise TimeoutError(f"workflow {self.workflow_id(task_id)} did not reach {wanted}")
            time.sleep(0.05)

    def stop(self) -> None:
        self.call(self.worker.shutdown())
        self.loop.call_soon_threadsafe(self.loop.stop)
