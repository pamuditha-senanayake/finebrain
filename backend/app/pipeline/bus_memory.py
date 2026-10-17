# bus_memory.py: in-memory event bus with the shape the Kafka adapter will keep (step 5).
# Used by: orchestrate.py, tests/test_chain.py. Uses: contracts_signal.py (Envelope), contracts_failure.py (DeadLetter).
from collections import deque
from collections.abc import Callable, MutableSet
from datetime import datetime

from pydantic import BaseModel

from app.pipeline.contracts_failure import DeadLetter
from app.pipeline.contracts_signal import Envelope

Handler = Callable[[Envelope], None]
DLQ_SUFFIX = ".dlq"


class MemoryBus:
    """A class because topics, subscribers and handled ids are state that publish and drain share."""

    def __init__(self, base: dict, now: datetime, new_id: Callable[[str], str], handled: MutableSet[str] | None = None):
        self.base = base  # tenant_id, cluster_id, env, branch: the same on every message
        self.now = now
        self.new_id = new_id
        self.topics: dict[str, list] = {}  # everything ever published, kept for tests and replay
        self.queue: deque[tuple[str, Envelope]] = deque()
        self.subscribers: dict[str, list[tuple[str, str, Handler]]] = {}
        self.handled = handled if handled is not None else set()  # "group:event_id"; a Valkey key set in production

    def publish(self, topic: str, event_type: str, payload: BaseModel, producer: str, cause: Envelope | None = None) -> Envelope:
        """Wrap the payload in the shared envelope. A cause carries its trace and correlation forward."""
        envelope = Envelope(
            event_id=self.new_id("evt"), event_type=event_type, schema_version=1, **self.base,
            occurred_at=self.now, recorded_at=self.now,
            trace_id=cause.trace_id if cause else self.new_id("trace"),
            correlation_id=cause.correlation_id if cause else self.new_id("corr"),
            causation_id=cause.event_id if cause else None,
            producer=producer, payload=payload.model_dump(mode="json"),
        )
        self.topics.setdefault(topic, []).append(envelope)
        self.queue.append((topic, envelope))
        return envelope

    def subscribe(self, topic: str, group: str, stage: str, handler: Handler) -> None:
        """One consumer group per stage, as on Kafka."""
        self.subscribers.setdefault(topic, []).append((group, stage, handler))

    def redeliver(self, topic: str, envelope: Envelope) -> None:
        """Kafka delivers at least once, so tests need to send a message again."""
        self.queue.append((topic, envelope))

    def drain(self) -> None:
        """Deliver queued messages in order until nothing is left, like consumers catching up."""
        while self.queue:
            topic, envelope = self.queue.popleft()
            for group, stage, handler in self.subscribers.get(topic, []):
                self.deliver(topic, group, stage, handler, envelope)

    def deliver(self, topic: str, group: str, stage: str, handler: Handler, envelope: Envelope) -> None:
        """Run a handler once per event_id. A failure becomes a DeadLetter instead of a crash."""
        key = f"{group}:{envelope.event_id}"
        if key in self.handled:
            return
        try:
            handler(envelope)
        except Exception as error:  # one catch per consumer, the entry point of each delivery
            self.dead_letter(topic, group, stage, envelope, error)
            return  # not marked handled, so a replay after a fix runs it again
        self.handled.add(key)

    def dead_letter(self, topic: str, group: str, stage: str, envelope: Envelope, error: Exception) -> None:
        """Keep the whole original, so a fix can replay it with the same event_id."""
        letter = DeadLetter(
            original=envelope, consumer_group=group, stage=stage, error_code=type(error).__name__,
            error_message=str(error)[:200], retryable=getattr(error, "retryable", False), attempts=1, failed_at=self.now,
        )
        self.topics.setdefault(topic + DLQ_SUFFIX, []).append(letter)

    def dead_letters(self, topic: str) -> list[DeadLetter]:
        """Every dead letter a topic's consumers produced."""
        return list(self.topics.get(topic + DLQ_SUFFIX, []))
