# s2_volume.py: the nightly volume run for S2. Sends many chat messages through S1 and S2 and checks the rules still hold.
# Run from backend/:  uv run python scripts/s2_volume.py [count] [--real]   (--real needs Docker: S3, Postgres, Valkey, Kafka)
# Exit code 1 if a rule breaks or S2 averages over its budget. Uses: capture_api.py, orchestrate.py, adapters.py.
import sys
import time
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, ".")
from app.pipeline import capture_api, fakes, orchestrate
from app.pipeline.adapters import make_memory_adapters, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.golden import NOW, SEED
from tests.test_s1_refund_chat import send

# Config
DEFAULT_COUNT = 2000
S2_BUDGET_SECONDS = 0.8  # the design budget for S1 and S2 together is 800 ms per signal
DUPLICATE_EVERY = 10  # one in ten messages is sent twice, to prove dedup holds at volume
REAL_PARTS = frozenset({"s3", "postgres", "valkey", "kafka"})
S2_TIMINGS: list[float] = []  # one entry per message S2 handled, duplicates included


def build_lane(real: bool, tag: str):
    seed = {**SEED, "tenant_id": f"volume_{tag}"} if real else SEED
    adapters = real_adapters(REAL_PARTS, topic_prefix=f"vol{tag}.") if real else make_memory_adapters
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, adapters)
    lane.bus.subscribers = {"signals.raw": [timed(entry) for entry in lane.bus.subscribers["signals.raw"]]}  # S1 and S2 only
    return lane


def timed(entry: tuple) -> tuple:
    """Wrap S2's handler so the run measures S2 itself, not the bus polling around it."""
    group, stage, handler = entry

    def run(envelope) -> None:
        started = time.perf_counter()
        handler(envelope)
        S2_TIMINGS.append(time.perf_counter() - started)

    return group, stage, run


def send_traffic(client, count: int) -> list[str]:
    """Send every message, some twice, with personal data inside. Returns the personal values sent."""
    secrets = []
    for number in range(count):
        email = f"volume{number}@example.lk"
        message = {"id": f"chat_msg_{number}", "text": f"Refund please, mail {email}"}
        send(client, message)
        send(client, message) if number % DUPLICATE_EVERY == 0 else None
        secrets.append(email)
    return secrets


def main() -> int:
    # Step 1: build the lane
    count = int(next((arg for arg in sys.argv[1:] if arg.isdigit()), DEFAULT_COUNT))
    real, tag = "--real" in sys.argv, uuid.uuid4().hex[:8]
    lane = build_lane(real, tag)

    # Step 2: S1 takes the traffic, then S2 works through everything it published
    secrets = send_traffic(TestClient(capture_api.create_app(lane)), count)
    started = time.perf_counter()
    lane.bus.drain()
    wall_per_signal = (time.perf_counter() - started) / count
    per_signal = sum(S2_TIMINGS) / len(S2_TIMINGS)

    # Step 3: check the rules and the speed
    signals = [envelope.payload for envelope in lane.bus.topics["signals.normalized"]]
    leaked = [value for value in secrets if value in str(signals)]
    rules_hold = len(signals) == count == len({signal["dedup_key"] for signal in signals}) and not leaked
    print(f"sent {count} (+{count // DUPLICATE_EVERY + 1} duplicates), signals {len(signals)}, personal values leaked {len(leaked)}")
    print(f"S2 {per_signal * 1000:.1f} ms per signal (wall clock with bus polling {wall_per_signal * 1000:.0f} ms), rules {'hold' if rules_hold else 'BROKEN'}")

    # Step 4: leave nothing behind on real infra
    if real:
        for uri in list(lane.object_store):
            del lane.object_store[uri]
        delete_prefixed_topics(f"vol{tag}.")
    return 0 if rules_hold and per_signal <= S2_BUDGET_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
