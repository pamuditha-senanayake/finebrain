# bus_kafka.py: the event bus on real Kafka (Redpanda locally), with the same methods as MemoryBus.
# Used by: tests/test_bus.py, orchestrate.py from step 6. Uses: contracts_signal.py (Envelope), contracts_failure.py (DeadLetter).
import time
from collections.abc import Callable
from datetime import datetime

from confluent_kafka import OFFSET_BEGINNING, Consumer, Message, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from pydantic import BaseModel

from app.pipeline.contracts_failure import DeadLetter
from app.pipeline.contracts_signal import Envelope

# Config
DEFAULT_BOOTSTRAP = "localhost:9092"
IDLE_SECONDS = 1.5  # drain stops after this long with no new message
POLL_SECONDS = 0.1
DLQ_SUFFIX = ".dlq"

Handler = Callable[[Envelope], None]


def broker_is_up(bootstrap: str = DEFAULT_BOOTSTRAP, timeout: float = 2.0) -> bool:
    """True when a broker answers, so tests can skip cleanly when Docker is down."""
    try:
        AdminClient({"bootstrap.servers": bootstrap}).list_topics(timeout=timeout)
    except Exception:
        return False
    return True


class KafkaBus:
    """A class because the producer, consumers, subscribers and handled ids are state publish and drain share."""

    def __init__(self, base: dict, now: datetime, new_id: Callable[[str], str], bootstrap: str = DEFAULT_BOOTSTRAP, topic_prefix: str = ""):
        self.base = base
        self.now = now
        self.new_id = new_id
        self.bootstrap = bootstrap
        self.topic_prefix = topic_prefix  # tests use a fresh prefix, so old messages never leak in
        self.producer = Producer({"bootstrap.servers": bootstrap, "enable.idempotence": True})
        self.admin = AdminClient({"bootstrap.servers": bootstrap})
        self.topics: dict[str, list] = {}  # what this process published, the same view MemoryBus gives
        self.subscribers: dict[str, list[tuple[str, str, Handler]]] = {}
        self.consumers: dict[str, Consumer] = {}  # one per consumer group
        self.handled: set[tuple[str, str]] = set()  # (group, event_id); moves to Valkey later

    # --- Publishing

    def publish(self, topic: str, event_type: str, payload: BaseModel, producer: str, cause: Envelope | None = None) -> Envelope:
        """Wrap the payload in the shared envelope and send it. A cause carries its trace and correlation forward."""
        envelope = Envelope(
            event_id=self.new_id("evt"), event_type=event_type, schema_version=1, **self.base,
            occurred_at=self.now, recorded_at=self.now,
            trace_id=cause.trace_id if cause else self.new_id("trace"),
            correlation_id=cause.correlation_id if cause else self.new_id("corr"),
            causation_id=cause.event_id if cause else None,
            producer=producer, payload=payload.model_dump(mode="json"),
        )
        self.send(topic, envelope, envelope.correlation_id)
        return envelope

    def redeliver(self, topic: str, envelope: Envelope) -> None:
        """Send the same envelope again, as Kafka may after a consumer crash."""
        self.send(topic, envelope, envelope.correlation_id)

    def send(self, topic: str, message: BaseModel, correlation_id: str) -> None:
        """Key by tenant and correlation, so one sample's messages keep their order."""
        self.ensure_topics([topic])
        key = f"{self.base['tenant_id']}:{correlation_id}"
        self.producer.produce(self.topic_prefix + topic, key=key, value=message.model_dump_json())
        self.topics.setdefault(topic, []).append(message)

    def ensure_topics(self, topics: list[str]) -> None:
        """Create missing topics with one partition. Real partition counts come with deployment."""
        missing = [self.topic_prefix + topic for topic in topics if topic not in self.topics]
        futures = self.admin.create_topics([NewTopic(name, num_partitions=1) for name in missing]) if missing else {}
        for future in futures.values():
            future.exception()  # wait; "already exists" is fine

    # --- Consuming

    def subscribe(self, topic: str, group: str, stage: str, handler: Handler) -> None:
        """One consumer group per stage. Partitions are assigned directly, so there is no rebalance wait."""
        self.ensure_topics([topic])
        self.subscribers.setdefault(topic, []).append((group, stage, handler))
        consumer = self.consumers.setdefault(group, Consumer({"bootstrap.servers": self.bootstrap, "group.id": self.topic_prefix + group}))
        wanted = {topic for topic, entries in self.subscribers.items() if any(entry[0] == group for entry in entries)}
        consumer.assign([TopicPartition(self.topic_prefix + name, 0, OFFSET_BEGINNING) for name in wanted])

    def drain(self) -> None:
        """Deliver until no consumer has seen a message for IDLE_SECONDS."""
        self.producer.flush()
        idle_since = time.monotonic()
        while time.monotonic() - idle_since < IDLE_SECONDS:
            if self.poll_once():
                idle_since = time.monotonic()
            self.producer.flush()

    def poll_once(self) -> bool:
        """Give every consumer group one chance to read. True when any message arrived."""
        got_any = False
        for group, consumer in self.consumers.items():
            message = consumer.poll(POLL_SECONDS)
            if message is not None and not message.error():
                self.handle(group, message)
                got_any = True
        return got_any

    def handle(self, group: str, message: Message) -> None:
        """Route one message to this group's handlers for its topic."""
        topic = message.topic().removeprefix(self.topic_prefix)
        envelope = Envelope.model_validate_json(message.value())
        for entry_group, stage, handler in self.subscribers.get(topic, []):
            if entry_group == group:
                self.deliver(topic, group, stage, handler, envelope)

    def deliver(self, topic: str, group: str, stage: str, handler: Handler, envelope: Envelope) -> None:
        """Run a handler once per event_id. A failure becomes a DeadLetter instead of a crash."""
        key = (group, envelope.event_id)
        if key in self.handled:
            return
        try:
            handler(envelope)
        except Exception as error:  # one catch per consumer, the entry point of each delivery
            self.dead_letter(topic, group, stage, envelope, error)
        self.handled.add(key)

    def dead_letter(self, topic: str, group: str, stage: str, envelope: Envelope, error: Exception) -> None:
        """Keep the whole original, so a fix can replay it with the same event_id."""
        letter = DeadLetter(
            original=envelope, consumer_group=group, stage=stage, error_code=type(error).__name__,
            error_message=str(error)[:200], retryable=False, attempts=1, failed_at=self.now,
        )
        self.send(topic + DLQ_SUFFIX, letter, envelope.correlation_id)
