# test_s7_s10_real.py: S1 to S10 on real infra (S9's runners as they are today). Anna's two visits on SeaweedFS, Postgres,
# Valkey and Redpanda, with the run records read back from Postgres; then on a real Temporal workflow that waits for her
# answer with a durable timer, resumes on it, and abandons the run when she never answers. Skips when services are down.
# Uses: orchestrate.py, adapters.py, temporal_flow.py, kafka_admin.py, tests/s7_world.py, tests/s6_world.py, tests/test_s5_real.py.
import time
import uuid

import pytest

from app.pipeline import orchestrate
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.s5_world import world_seed
from tests.s6_world import ask, refund, scripted
from tests.s7_world import actions, full_lane, runs, says
from tests.test_s1_real import read_topic
from tests.test_s1_refund_chat import FIRST, SECOND
from tests.test_s5_real import S5_PARTS, parts

# Config
WAIT_FOR_WORKFLOW_SECONDS = 30


def seed_for(tag: str, **extra) -> dict:
    return {**world_seed(), "tenant_id": f"test_{tag}", **extra}


def wait_until_done(lane, task_id: str) -> str:
    """The workflow goes on by itself after a signal; wait until it rests."""
    deadline = time.monotonic() + WAIT_FOR_WORKFLOW_SECONDS
    while time.monotonic() < deadline:
        phase = lane.runner.progress(task_id)["phase"]
        if phase == "done":
            return phase
        time.sleep(0.5)
    return phase


@pytest.mark.skipif(bool(missing_infra(S5_PARTS)), reason="infra not answering")
def test_anna_is_asked_then_refunded_on_real_infra():
    tag = uuid.uuid4().hex[:8]
    lane = full_lane(real_adapters(parts(), topic_prefix=f"s10{tag}."), seed=seed_for(tag))
    try:
        lane.model, _ = scripted(ask(), refund())
        says(lane, FIRST)
        says(lane, SECOND)
        run_id = lane.bus.topics["runs.completed"][-1].payload["run_id"]
        assert [v["outcome"] for v in lane.records.history("run", run_id)] == ["awaiting_customer", "resolved"]  # from Postgres
        assert lane.records.load("run", run_id)["decided_by"] == "auto by policy"
        executed = [m["payload"]["tool_id"] for m in read_topic(f"s10{tag}.actions.executed", 2)]  # from Redpanda
        assert executed == ["tool_reply_email", "tool_payment_refund"]
    finally:
        delete_prefixed_topics(f"s10{tag}.")


@pytest.mark.skipif(bool(missing_infra(frozenset({"temporal"}))), reason="no Temporal on localhost:7233")
def test_on_temporal_the_workflow_waits_for_the_answer_then_refunds():
    lane = full_lane(real_adapters(frozenset({"temporal"})), seed=seed_for(uuid.uuid4().hex[:8]))
    try:
        lane.model, _ = scripted(ask(), refund())
        says(lane, FIRST)
        first_task = lane.bus.topics["tasks.created"][0].payload["task_id"]
        assert lane.runner.progress(first_task)["phase"] == "awaiting_customer"  # a durable wait, not a closed run
        says(lane, SECOND)  # S4 joins it and signals the waiting workflow
        assert wait_until_done(lane, first_task) == "done"
        assert actions(lane)[-1] == ("tool_payment_refund", "succeeded") and list(runs(lane).values())[0] == ["awaiting_customer", "resolved"]
    finally:
        orchestrate.close_lane(lane)


@pytest.mark.skipif(bool(missing_infra(frozenset({"temporal"}))), reason="no Temporal on localhost:7233")
def test_on_temporal_no_answer_abandons_the_run_when_the_timer_ends():
    lane = full_lane(real_adapters(frozenset({"temporal"})), seed=seed_for(uuid.uuid4().hex[:8], customer_wait_seconds=2))
    try:
        lane.model, _ = scripted(ask())
        says(lane, FIRST)
        first_task = lane.bus.topics["tasks.created"][0].payload["task_id"]
        assert wait_until_done(lane, first_task) == "done"
        assert list(runs(lane).values())[0] == ["awaiting_customer", "abandoned"] and ("tool_payment_refund", "succeeded") not in actions(lane)
    finally:
        orchestrate.close_lane(lane)
