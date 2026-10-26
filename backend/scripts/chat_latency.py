# chat_latency.py: how long a website visitor waits for the brain's reply, without the model's own thinking time. Landing
# page chat is built through Studio; each visitor message goes in through the real S1 inbound path and out through the
# connection's reply action, on real Postgres, Valkey, Redpanda and S3 (a scripted model, a stand-in site), timed from
# arrival to the reply being posted. Run from backend/:  uv run python scripts/chat_latency.py [messages]
# Exit code 1 if the median is over budget. Uses: tests/activity_world.py, adapters.py, bus_kafka.py.
import statistics
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, ".")
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.activity_world import answer_with, build, build_landing, stand_in_portal, visitor
from tests.s6_world import scripted
from tests.test_s5_real import S5_PARTS, parts

# Config
DEFAULT_MESSAGES = 10
BUDGET_SECONDS = 1.0  # S1 to S9 for one chat message, before the model's own time is added
PARTS = frozenset(S5_PARTS) | ({"temporal"} if "--temporal" in sys.argv else set())  # what HQ runs on; --temporal adds its workflows


def measure(lane, posted: list, number: int) -> float:
    """One message: from the visitor's message arriving to the reply being posted, by the site's own stamp on the reply
    (visitor() returns only once the bus has been idle a while, so its return time would overstate the wait)."""
    before = len(posted)
    started = datetime.now(timezone.utc)
    visitor(lane, f"Hello, question {number}", conversation=f"c-latency-{number}")
    if len(posted) == before:
        return float("inf")
    return (datetime.fromisoformat(posted[-1]["at"]) - started).total_seconds()


if __name__ == "__main__":
    if missing_infra(PARTS):
        raise SystemExit(f"Start Docker first: {', '.join(missing_infra(PARTS))} not answering")
    count = int(next((a for a in sys.argv[1:] if a.isdigit()), DEFAULT_MESSAGES))
    tag, patch = uuid.uuid4().hex[:8], pytest.MonkeyPatch()
    client, lane = build(real_adapters(PARTS, topic_prefix=f"lat{tag}."), tenant=f"lat_{tag}")
    try:
        posted = stand_in_portal(patch)
        ids = build_landing(client, lane)
        lane.model, _ = scripted(*[answer_with(ids["policy"], f"Reply {n}") for n in range(count)])
        timings = [measure(lane, posted, n) for n in range(count)]
        median, worst = statistics.median(timings), max(timings)
        print(f"{count} chat messages on Postgres, Valkey, Redpanda and S3 (no model time)")
        print(f"arrival to reply posted: median {median:.2f} s, worst {worst:.2f} s (budget {BUDGET_SECONDS:.1f} s)")
        sys.exit(1 if median > BUDGET_SECONDS else 0)
    finally:
        patch.undo()
        delete_prefixed_topics(f"lat{tag}.")
