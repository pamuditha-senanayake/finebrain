# s1_volume.py: the nightly volume run for S1. Sends many signed chat messages and checks the rules still hold.
# Run from backend/:  uv run python scripts/s1_volume.py [count] [--real]   (--real needs Docker: S3 and Kafka)
# Exit code 1 if a rule breaks or the slowest 5% is over the limit. Uses: capture_api.py, orchestrate.py, adapters.py.
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
DEFAULT_COUNT = 5000
P95_LIMIT_SECONDS = 0.25  # the design budget for S1 and S2 together is 800 ms
BAD_EVERY = 10  # one in ten messages is signed wrongly, to prove refusals still store nothing


def build_lane(real: bool, tag: str):
    seed = {**SEED, "tenant_id": f"volume_{tag}"} if real else SEED
    adapters = real_adapters(frozenset({"s3", "kafka"}), topic_prefix=f"vol{tag}.") if real else make_memory_adapters
    return orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, adapters)


def run_traffic(client, count: int) -> tuple[list[float], list[str]]:
    """Send every message, return each answer time and the ids that were accepted."""
    timings, accepted = [], []
    for number in range(count):
        message = {"id": f"chat_msg_{number}", "text": f"refund question number {number}"}
        started = time.perf_counter()
        status = send(client, message, secret="wrong" if number % BAD_EVERY == 0 else None).status_code
        timings.append(time.perf_counter() - started)
        accepted += [message["id"]] if status == 202 else []
    return timings, accepted


def main() -> int:
    # Step 1: build the lane
    count = int(next((arg for arg in sys.argv[1:] if arg.isdigit()), DEFAULT_COUNT))
    real, tag = "--real" in sys.argv, uuid.uuid4().hex[:8]
    lane = build_lane(real, tag)

    # Step 2: send the traffic
    timings, accepted = run_traffic(TestClient(capture_api.create_app(lane)), count)
    lane.bus.flush() if real else None

    # Step 3: check the rules and the speed
    published = [envelope.payload["external_id"] for envelope in lane.bus.topics["signals.raw"]]
    p95 = sorted(timings)[int(len(timings) * 0.95)]
    rules_hold = published == accepted and len(lane.object_store) == len(accepted)
    print(f"sent {count}, accepted {len(accepted)}, stored {len(lane.object_store)}, published {len(published)}")
    print(f"{count / sum(timings):.0f} per second, p95 {p95 * 1000:.0f} ms, rules {'hold' if rules_hold else 'BROKEN'}")

    # Step 4: leave nothing behind on real infra
    if real:
        for uri in list(lane.object_store):
            del lane.object_store[uri]
        delete_prefixed_topics(f"vol{tag}.")
    return 0 if rules_hold and p95 <= P95_LIMIT_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
