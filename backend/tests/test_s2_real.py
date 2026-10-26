# test_s2_real.py: S2 on real SeaweedFS, Redpanda, Valkey and Postgres. Anna's chat messages, read back from the real topic.
# Skips when the services do not answer. Start them with backend/scripts/dev_up.sh.
# Uses: orchestrate.py, adapters.py, tests/test_s1_real.py (read_topic), tests/test_s1_refund_chat.py (helpers).
import uuid

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.golden import NOW, SEED
from tests.test_s1_real import read_topic
from tests.test_s1_refund_chat import CONVERSATION, FIRST, SECOND, send

# Config
S2_PARTS = frozenset({"s3", "postgres", "valkey", "kafka"})  # object store, vault, dedup keys, bus


# --- Helpers

@pytest.fixture
def real_lane():
    """A lane with S1 and S2 only, on real infra, with a fresh tenant and topic prefix."""
    missing = missing_infra(S2_PARTS)
    if missing:
        pytest.skip(f"infra not answering: {', '.join(missing)}")
    observe.reset_counts()
    tag = uuid.uuid4().hex[:8]
    seed = {**SEED, "tenant_id": f"test_{tag}"}
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, real_adapters(S2_PARTS, topic_prefix=f"s2{tag}."))
    lane.bus.subscribers = {"signals.raw": lane.bus.subscribers["signals.raw"]}
    yield lane, tag
    for uri in list(lane.object_store):
        del lane.object_store[uri]  # a test run leaves no objects behind
    delete_prefixed_topics(f"s2{tag}.")


# --- Anna's messages through real infra

def test_anna_messages_become_signals_on_the_real_topic(real_lane):
    lane, tag = real_lane
    client = TestClient(capture_api.create_app(lane))
    for message in (FIRST, SECOND):
        assert send(client, message).status_code == 202
    lane.bus.drain()
    signals = [message["payload"] for message in read_topic(f"s2{tag}.signals.normalized", 2)]
    assert [signal["dedup_key"].split(":")[-1] for signal in signals] == [FIRST["id"], SECOND["id"]]
    assert {signal["conversation_id"] for signal in signals} == {CONVERSATION}
    assert not [secret for secret in ("Anna", "anna@example.lk") if secret in str(signals)]


def test_valkey_drops_the_second_copy_of_a_message(real_lane):
    lane, tag = real_lane
    client = TestClient(capture_api.create_app(lane))
    send(client, FIRST), send(client, FIRST)
    lane.bus.drain()
    assert len(read_topic(f"s2{tag}.signals.normalized", 2)) == 1 and observe.read_count("s2.duplicate") == 1
