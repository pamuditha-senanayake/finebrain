# test_s3_real.py: S3 on real infra. Anna's refund request routed from the graph in Postgres, the task read back from
# Redpanda, and one real Claude call through the Planner fallback. Skips when the services or the API key are missing.
# Uses: orchestrate.py, adapters.py, stages_route.py, llm.py, scripts/test_keys.py, tests/test_s1_real.py, tests/test_s3_planner.py.
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, llm, observe, orchestrate, stages_route
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from scripts.test_keys import ENV_PATH, load_env_file
from tests.golden import NOW, SEED
from tests.test_s1_real import read_topic
from tests.test_s1_refund_chat import FIRST, send
from tests.test_s3_planner import ANNA, NO_KEYWORD, ROUTING

# Config
S3_PARTS = frozenset({"s3", "postgres", "valkey", "kafka"})  # object store, vault and graph, dedup keys, bus


# --- Helpers

@pytest.fixture
def real_lane():
    """S1 to S3 on real infra, with a fresh tenant and topic prefix."""
    missing = missing_infra(S3_PARTS)
    if missing:
        pytest.skip(f"infra not answering: {', '.join(missing)}")
    observe.reset_counts()
    tag = uuid.uuid4().hex[:8]
    seed = {**SEED, "tenant_id": f"test_{tag}"}
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, real_adapters(S3_PARTS, topic_prefix=f"s3{tag}."))
    lane.bus.subscribers = {topic: lane.bus.subscribers[topic][:1] for topic in ("signals.raw", "signals.normalized")}
    yield lane, tag
    for uri in list(lane.object_store):
        del lane.object_store[uri]  # a test run leaves no objects behind
    delete_prefixed_topics(f"s3{tag}.")


# --- Anna's request, routed from the real graph onto the real topic

def test_anna_request_becomes_a_refund_task_on_kafka(real_lane):
    lane, tag = real_lane
    assert send(TestClient(capture_api.create_app(lane)), FIRST).status_code == 202
    lane.bus.drain()
    [task] = [message["payload"] for message in read_topic(f"s3{tag}.tasks.created", 1)]
    assert (task["resolver_rule_id"], task["agent_id"], task["skill_ref"]["version"]) == ("rr_refund_chat", "agent_refund_worker", 3)
    assert read_topic(f"s3{tag}.tasks.unrouted", 1) == []


# --- The Planner fallback with a real Claude call

def test_real_claude_plans_a_refund_without_the_word_refund():
    load_env_file(ENV_PATH)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY in backend/.env")
    task, reason = stages_route.route(ANNA.model_copy(update={"text_masked": NO_KEYWORD}), ROUTING, llm.make_chooser(), NOW)
    assert (reason, task.resolver_rule_id) == ("planned", "rr_refund_chat")
    assert stages_route.PLANNED_FLAG in task.flags
