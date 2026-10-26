# test_s1_real.py: S1 on real SeaweedFS (S3) and Redpanda (Kafka). Anna's two chat messages, read back from the real stores.
# Skips when the services do not answer. Start them with backend/scripts/dev_up.sh.
# Uses: capture_api.py, orchestrate.py, adapters.py, store_s3.py, kafka_admin.py, tests/test_s1_refund_chat.py (helpers).
import json
import uuid

import pytest
from confluent_kafka import Consumer, TopicPartition, OFFSET_BEGINNING
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate, store_s3
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import DEFAULT_BOOTSTRAP, delete_prefixed_topics
from tests.golden import NOW, SEED
from tests.test_s1_refund_chat import FIRST, SECOND, send

# Config
S1_PARTS = frozenset({"s3", "kafka"})
POLL_SECONDS = 10


# --- Helpers

@pytest.fixture
def real_lane():
    """A lane whose object store and bus are real, on a fresh tenant and topic prefix."""
    missing = missing_infra(S1_PARTS)
    if missing:
        pytest.skip(f"infra not answering: {', '.join(missing)}")
    observe.reset_counts()
    tag = uuid.uuid4().hex[:8]
    seed = {**SEED, "tenant_id": f"test_{tag}"}
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, real_adapters(S1_PARTS, topic_prefix=f"s1{tag}."))
    yield lane, tag
    for uri in list(lane.object_store):
        del lane.object_store[uri]  # a test run leaves no objects behind
    delete_prefixed_topics(f"s1{tag}.")


def read_topic(topic: str, count: int) -> list[dict]:
    """Read a topic from the start with a fresh consumer, the way another service would."""
    consumer = Consumer({"bootstrap.servers": DEFAULT_BOOTSTRAP, "group.id": uuid.uuid4().hex})
    consumer.assign([TopicPartition(topic, 0, OFFSET_BEGINNING)])
    messages = []
    for _ in range(POLL_SECONDS):
        message = consumer.poll(1.0)
        messages += [json.loads(message.value())] if message and not message.error() else []
        if len(messages) == count:
            break
    consumer.close()
    return messages


# --- Anna's two messages through real storage and a real broker

def test_anna_messages_land_in_s3_and_on_kafka(real_lane):
    lane, tag = real_lane
    client = TestClient(capture_api.create_app(lane))
    assert [send(client, message).status_code for message in (FIRST, SECOND)] == [202, 202]
    lane.bus.flush()

    # Step 1: the raw bodies are in S3, read back through a fresh connection
    fresh = store_s3.S3ObjectStore(store_s3.connect(), prefix=f"{lane.seed['tenant_id']}/")
    assert len(fresh) == 2 and all(b"Anna" in fresh[uri] for uri in fresh)

    # Step 2: both K1 messages are on the real topic, in order
    on_kafka = read_topic(f"s1{tag}.signals.raw", 2)
    assert [message["payload"]["external_id"] for message in on_kafka] == [FIRST["id"], SECOND["id"]]
