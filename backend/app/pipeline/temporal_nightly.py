# temporal_nightly.py: the night jobs on Temporal: S13's review at 02:00 (step 15) and the Distiller at 03:00 (step 13d), in
# the tenant's time zone. A Temporal Schedule starts each job's workflow; its one activity runs the callback the API gives.
# Each job has its own task queue and worker on the lane's runner. Without Temporal, "Run now" on the console stands in.
# Used by: api/hq.py (start, start_distiller), tests/test_nightly.py, test_summary.py. Uses: temporal_runner.py (client and loop).
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleAlreadyRunningError, ScheduleSpec
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

# Config
TIMEOUT = timedelta(minutes=30)  # Claude writes one draft or summary at a time
ONCE = RetryPolicy(maximum_attempts=1)  # a retry would draft or write again, so a failure waits for the next night


@workflow.defn(name="NightlyWorkflow")
class NightlyWorkflow:
    """02:00: the nightly review."""

    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity("nightly_review", start_to_close_timeout=TIMEOUT, retry_policy=ONCE)


@workflow.defn(name="DistillerWorkflow")
class DistillerWorkflow:
    """03:00: the Distiller."""

    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity("distill", start_to_close_timeout=TIMEOUT, retry_policy=ONCE)


# Config: job name to (workflow, activity, schedule id prefix, cron)
JOBS = {"nightly": (NightlyWorkflow, "nightly_review", "nightly", "0 2 * * *"), "distiller": (DistillerWorkflow, "distill", "distiller", "0 3 * * *")}


def names(tenant_id: str, job: str = "nightly") -> tuple[str, str]:
    """The schedule id and the task queue, one of each per tenant and job."""
    prefix = JOBS[job][2]
    return f"{prefix}-{tenant_id}", f"{prefix}-{tenant_id}"


def start_job(runner, tenant_id: str, zone: str, job: str, callback) -> str:
    """Serve the job on this runner and make sure its schedule exists. A restart finds it there and keeps it. Returns its id."""
    flow, activity_name, _, cron = JOBS[job]
    schedule_id, queue = names(tenant_id, job)

    @activity.defn(name=activity_name)
    def run_job() -> dict:
        return callback()

    async def make_worker() -> Worker:  # made on the loop it runs on; the job blocks for minutes, so it runs on its own thread, never on the shared loop
        return Worker(runner.client, task_queue=queue, workflows=[flow], activities=[run_job], activity_executor=ThreadPoolExecutor(max_workers=1))

    worker = runner.call(make_worker())
    asyncio.run_coroutine_threadsafe(worker.run(), runner.loop)
    schedule = Schedule(action=ScheduleActionStartWorkflow(flow.run, id=f"{schedule_id}-run", task_queue=queue), spec=ScheduleSpec(cron_expressions=[cron], time_zone_name=zone))
    try:
        runner.call(runner.client.create_schedule(schedule_id, schedule))
    except ScheduleAlreadyRunningError:
        pass  # made by an earlier start; its worker is this one now
    return schedule_id


def start(runner, tenant_id: str, zone: str, run_review) -> str:
    return start_job(runner, tenant_id, zone, "nightly", run_review)


def start_distiller(runner, tenant_id: str, zone: str, run_distiller) -> str:
    return start_job(runner, tenant_id, zone, "distiller", run_distiller)
