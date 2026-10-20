# temporal_nightly.py: step 15, S13's nightly review on Temporal (the design's nightly_review). A Temporal Schedule starts
# NightlyWorkflow at 02:00 in the tenant's time zone; its one activity runs the review through the callback the API gives.
# Its own task queue and worker on the lane's runner, like readiness. Without Temporal, "Run overnight review now" stands in.
# Used by: api/hq.py (start), tests/test_nightly.py. Uses: temporal_runner.py (client and loop).
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleAlreadyRunningError, ScheduleSpec
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

# Config
AT = "0 2 * * *"  # 02:00 every night
ACTIVITY = "nightly_review"
TIMEOUT = timedelta(minutes=30)  # Claude drafts one fix per group of wrong runs


@workflow.defn(name="NightlyWorkflow")
class NightlyWorkflow:
    """One night: run the review once. A retry would draft again, so it runs once and a failure waits for the next night."""

    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(ACTIVITY, start_to_close_timeout=TIMEOUT, retry_policy=RetryPolicy(maximum_attempts=1))


def names(tenant_id: str) -> tuple[str, str]:
    """The schedule id and the task queue, one of each per tenant."""
    return f"nightly-{tenant_id}", f"nightly-{tenant_id}"


def start(runner, tenant_id: str, zone: str, run_review) -> str:
    """Serve the review on this runner and make sure the nightly schedule exists. A restart finds it there and keeps it. Returns its id."""
    schedule_id, queue = names(tenant_id)

    @activity.defn(name=ACTIVITY)
    def nightly_review() -> dict:
        return run_review()

    async def make_worker() -> Worker:  # made on the loop it runs on; the review blocks for minutes, so it runs on its own thread, never on the shared loop
        return Worker(runner.client, task_queue=queue, workflows=[NightlyWorkflow], activities=[nightly_review], activity_executor=ThreadPoolExecutor(max_workers=1))

    worker = runner.call(make_worker())
    asyncio.run_coroutine_threadsafe(worker.run(), runner.loop)
    schedule = Schedule(action=ScheduleActionStartWorkflow(NightlyWorkflow.run, id=f"{schedule_id}-run", task_queue=queue),
                        spec=ScheduleSpec(cron_expressions=[AT], time_zone_name=zone))
    try:
        runner.call(runner.client.create_schedule(schedule_id, schedule))
    except ScheduleAlreadyRunningError:
        pass  # made by an earlier start; its worker is this one now
    return schedule_id
