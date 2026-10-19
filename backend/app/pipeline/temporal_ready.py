# temporal_ready.py: step 16 slice 4, S15's hourly tick on Temporal (D01). A Temporal Schedule starts ReadinessWorkflow every hour;
# its one activity runs the readiness check through the callback the API gives (which also tells people). It has its own task queue
# and worker on the lane's runner, so it never mixes with run work. Without Temporal, the screens' hourly check-on-read stands in.
# Used by: api/hq.py (start), tests/test_ready_time.py. Uses: temporal_runner.py (client and loop).
import asyncio
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleAlreadyRunningError, ScheduleIntervalSpec, ScheduleSpec
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

# Config
EVERY = timedelta(hours=1)  # the design's readiness tick
ACTIVITY = "readiness_check"
TIMEOUT = timedelta(minutes=2)


@workflow.defn(name="ReadinessWorkflow")
class ReadinessWorkflow:
    """One tick: run the check once, retried twice if the worker hiccups."""

    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(ACTIVITY, start_to_close_timeout=TIMEOUT, retry_policy=RetryPolicy(maximum_attempts=3))


def names(tenant_id: str) -> tuple[str, str]:
    """The schedule id and the task queue, one of each per tenant."""
    return f"readiness-{tenant_id}", f"readiness-{tenant_id}"


def start(runner, tenant_id: str, run_check) -> str:
    """Serve the tick on this runner and make sure the hourly schedule exists. A restart finds it there and keeps it. Returns its id."""
    schedule_id, queue = names(tenant_id)

    @activity.defn(name=ACTIVITY)
    async def readiness_check() -> dict:
        return run_check()

    async def make_worker() -> Worker:  # a worker must be made on the loop it runs on
        return Worker(runner.client, task_queue=queue, workflows=[ReadinessWorkflow], activities=[readiness_check])

    worker = runner.call(make_worker())
    asyncio.run_coroutine_threadsafe(worker.run(), runner.loop)
    schedule = Schedule(action=ScheduleActionStartWorkflow(ReadinessWorkflow.run, id=f"{schedule_id}-tick", task_queue=queue),
                        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=EVERY)]))
    try:
        runner.call(runner.client.create_schedule(schedule_id, schedule))
    except ScheduleAlreadyRunningError:
        pass  # made by an earlier start; its worker is this one now
    return schedule_id
