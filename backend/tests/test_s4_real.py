# test_s4_real.py: S4 on real infra. Anna's two visits run S1 to S4 on SeaweedFS, Postgres (records, graph), Valkey (claims)
# and Redpanda, with S4 wired on the bus and nothing after it; two workers with their own connections race on one chat;
# a follow-up reaches a running Temporal workflow. Skips when the services are not answering.
# Uses: orchestrate.py, stages_orchestrate.py, stages_orchestrate_chat.py, adapters.py, kafka_admin.py, tests/test_s1_real.py,
# tests/test_s1_refund_chat.py, tests/test_decide.py (a run waiting for approval on Temporal).
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate, stages_orchestrate
from app.pipeline import stages_orchestrate_chat as chat
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.golden import NOW, SEED
from tests.test_decide import waiting_lane
from tests.test_s1_real import read_topic
from tests.test_s1_refund_chat import FIRST, SECOND, SESSION, send

# Config
S4_PARTS = frozenset({"s3", "postgres", "valkey", "kafka"})  # raw store, records and graph, claims, bus


# --- Helpers

def unique_ids(worker: str):
    """Ids no other worker or test run can repeat, as a live tenant uses."""
    return lambda prefix: f"{prefix}_{worker}_{uuid.uuid4().hex[:10]}"


def build(seed: dict, tag: str, worker: str = "w1"):
    """S1 to S4 on real infra; S4 is wired on tasks.created and stops there, so S5 onwards never run."""
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW,
                                  real_adapters(S4_PARTS, topic_prefix=f"s4{tag}."), new_id=unique_ids(worker))
    lane.bus.subscribers = {topic: lane.bus.subscribers[topic][:1] for topic in ("signals.raw", "signals.normalized")}
    lane.bus.subscribe("tasks.created", "worker", "S4", lambda envelope: stages_orchestrate.begin_run(lane, envelope))
    return lane


@pytest.fixture
def real():
    missing = missing_infra(S4_PARTS)
    if missing:
        pytest.skip(f"infra not answering: {', '.join(missing)}")
    observe.reset_counts()
    tag = uuid.uuid4().hex[:8]
    seed = {**SEED, "tenant_id": f"test_{tag}"}
    lanes = []
    yield lambda worker="w1": lanes.append(build(seed, tag, worker)) or lanes[-1], tag
    for lane in lanes[:1]:
        for uri in list(lane.object_store):
            del lane.object_store[uri]  # a test run leaves no objects behind
    delete_prefixed_topics(f"s4{tag}.")


# --- Anna's two visits, S1 to S4, on real infra

def test_visit_1_starts_a_run_and_visit_2_joins_it_on_real_infra(real):
    make, tag = real
    lane = make()
    client = TestClient(capture_api.create_app(lane))
    assert send(client, FIRST).status_code == 202
    lane.bus.drain()
    [started] = [message["payload"] for message in read_topic(f"s4{tag}.runs.started", 1)]
    assert (started["agent_id"], started["recipe"]["skill_ref"]["version"], started["handoff"]["conversation_id"]) == ("agent_refund_worker", 3, SESSION)

    # Visit 2: no rule matches "yes, that one"; S3 finds the open run in Postgres and S4 joins it
    assert send(client, SECOND).status_code == 202
    lane.bus.drain()
    [joined] = [message["payload"] for message in read_topic(f"s4{tag}.runs.continued", 1)]
    assert joined["run_id"] == started["run_id"] and len(joined["transcript_signal_ids"]) == 2
    assert [message.signal_id for message in chat.inbox(lane, started["run_id"])] == [joined["signal_id"]]  # read back from Postgres
    assert len(read_topic(f"s4{tag}.runs.started", 2)) == 1  # still one run


def test_two_workers_racing_on_one_chat_make_one_run(real):
    make, tag = real
    first, second = make("w1"), make("w2")  # two processes: their own Postgres connections and Valkey clients
    for lane in (first, second):
        lane.bus.subscribers.pop("tasks.created")  # each test thread hands its task to its own worker
    client = TestClient(capture_api.create_app(first))
    assert send(client, FIRST).status_code == 202
    assert send(client, {"id": "chat_msg_anna_r", "text": "please refund my last order"}).status_code == 202
    first.bus.drain()
    task_a, task_b = first.bus.topics["tasks.created"][-2:]
    threads = [threading.Thread(target=stages_orchestrate.begin_run, args=(lane, task)) for lane, task in ((first, task_a), (second, task_b))]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]
    started = read_topic(f"s4{tag}.runs.started", 2)
    continued = read_topic(f"s4{tag}.runs.continued", 2)
    assert (len(started), len(continued)) == (1, 1) and continued[0]["payload"]["run_id"] == started[0]["payload"]["run_id"]


# --- A follow-up reaches a running Temporal workflow

@pytest.mark.skipif(bool(missing_infra(frozenset({"temporal"}))), reason="no Temporal on localhost:7233")
def test_a_joined_message_reaches_the_running_temporal_workflow():
    seed = {**SEED, "tenant_id": f"test_{uuid.uuid4().hex[:8]}"}
    lane, _, _ = waiting_lane(seed, real_adapters(frozenset({"temporal"})))  # a refund run paused for approval
    try:
        task_id = lane.bus.topics["tasks.created"][-1].payload["task_id"]
        envelope = lane.bus.topics["tasks.created"][-1]
        chat.signal_workflow(lane, task_id, envelope)
        assert lane.runner.progress(task_id) == {"phase": "awaiting_approval", "handled": 0, "messages": 1}
    finally:
        orchestrate.close_lane(lane)
