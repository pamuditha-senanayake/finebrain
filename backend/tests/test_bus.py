# test_bus.py: the same bus checks run on MemoryBus and on KafkaBus, so both behave alike.
# Kafka tests are skipped when no broker answers on localhost:9092 (start it with backend/infra/compose.yaml).
# Uses: app/pipeline/bus_memory.py, app/pipeline/bus_kafka.py, app/pipeline/fakes.py, tests/golden.py.
import uuid

import pytest
from confluent_kafka import OFFSET_BEGINNING, Consumer, TopicPartition

from app.pipeline import fakes
from app.pipeline.bus_kafka import DEFAULT_BOOTSTRAP, KafkaBus, broker_is_up
from app.pipeline.bus_memory import MemoryBus
from app.pipeline.contracts_failure import DeadLetter
from app.pipeline.contracts_signal import Subject
from app.pipeline.retry import replay_dead_letters
from tests.golden import NOW, SEED

# Config
BASE = {"tenant_id": SEED["tenant_id"], "cluster_id": SEED["cluster_id"], "env": SEED["env"], "branch": "main"}
KAFKA_UP = broker_is_up()
PAYLOAD = Subject(entity_type="payment", entity_ref="pay_FB_20261004_0192")


# --- Helpers

@pytest.fixture(params=["memory", "kafka"])
def bus(request):
    """Each test runs once per bus. Kafka gets a fresh topic prefix so earlier runs never leak in."""
    if request.param == "memory":
        return MemoryBus(BASE, NOW, fakes.make_id_maker())
    if not KAFKA_UP:
        pytest.skip("no Kafka broker on localhost:9092")
    return KafkaBus(BASE, NOW, fakes.make_id_maker(), topic_prefix=f"test{uuid.uuid4().hex[:8]}.")


def collect(bus, topic: str, group: str, stage: str = "S2") -> list:
    """Subscribe a handler that only remembers what it received."""
    received = []
    bus.subscribe(topic, group, stage, received.append)
    return received


# --- Checks on both buses

def test_published_message_arrives_whole(bus):
    received = collect(bus, "signals.raw", "normalizer")
    sent = bus.publish("signals.raw", "signal.raw.captured", PAYLOAD, "capture")
    bus.drain()
    assert received == [sent]


def test_handler_output_keeps_correlation_and_cause(bus):
    downstream = collect(bus, "signals.normalized", "resolver", "S3")
    bus.subscribe("signals.raw", "normalizer", "S2", lambda env: bus.publish("signals.normalized", "signal.normalized", PAYLOAD, "normalizer", env))
    first = bus.publish("signals.raw", "signal.raw.captured", PAYLOAD, "capture")
    bus.drain()
    assert [(env.correlation_id, env.causation_id) for env in downstream] == [(first.correlation_id, first.event_id)]


def test_redelivered_event_is_handled_once(bus):
    received = collect(bus, "signals.raw", "normalizer")
    sent = bus.publish("signals.raw", "signal.raw.captured", PAYLOAD, "capture")
    bus.redeliver("signals.raw", sent)
    bus.drain()
    assert len(received) == 1


def test_every_group_gets_its_own_copy(bus):
    normalizer = collect(bus, "signals.raw", "normalizer")
    auditor = collect(bus, "signals.raw", "auditor", "S10")
    bus.publish("signals.raw", "signal.raw.captured", PAYLOAD, "capture")
    bus.drain()
    assert len(normalizer) == len(auditor) == 1


def test_failing_handler_goes_to_dead_letter(bus):
    def broken(envelope):
        raise ValueError("cannot parse")

    bus.subscribe("signals.raw", "normalizer", "S2", broken)
    sent = bus.publish("signals.raw", "signal.raw.captured", PAYLOAD, "capture")
    bus.drain()
    letters = bus.topics["signals.raw.dlq"]
    assert [(letter.stage, letter.error_code, letter.original.event_id) for letter in letters] == [("S2", "ValueError", sent.event_id)]


def test_replay_after_a_fix_runs_the_handler(bus):
    state, received = {"broken": True}, []

    def handler(envelope):
        if state["broken"]:
            raise ValueError("bug")
        received.append(envelope)

    bus.subscribe("signals.raw", "normalizer", "S2", handler)
    sent = bus.publish("signals.raw", "signal.raw.captured", PAYLOAD, "capture")
    bus.drain()
    state["broken"] = False  # the bug is fixed and deployed
    assert replay_dead_letters(bus, "signals.raw") == 1
    bus.drain()
    assert received == [sent]


# --- Kafka only: the dead letter is really on the broker, not just in memory

@pytest.mark.skipif(not KAFKA_UP, reason="no Kafka broker on localhost:9092")
def test_dead_letter_is_readable_from_the_broker():
    prefix = f"test{uuid.uuid4().hex[:8]}."
    bus = KafkaBus(BASE, NOW, fakes.make_id_maker(), topic_prefix=prefix)
    bus.subscribe("signals.raw", "normalizer", "S2", lambda envelope: 1 / 0)
    bus.publish("signals.raw", "signal.raw.captured", PAYLOAD, "capture")
    bus.drain()
    bus.producer.flush()

    reader = Consumer({"bootstrap.servers": DEFAULT_BOOTSTRAP, "group.id": prefix + "reader"})
    reader.assign([TopicPartition(prefix + "signals.raw.dlq", 0, OFFSET_BEGINNING)])
    message = reader.poll(10)
    reader.close()
    assert DeadLetter.model_validate_json(message.value()).error_code == "ZeroDivisionError"
