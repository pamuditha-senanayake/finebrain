# s4_volume.py: the nightly volume run for S4. Many chats, each with a refund ask, a confirmation and sometimes a third
# message, run S1 to S4 the way the consumers do; S4 stops the pipeline, so only S1 to S4 is timed and checked.
# Run from backend/:  uv run python scripts/s4_volume.py [chats] [--real]   (--real needs Docker: S3, Postgres, Valkey, Kafka)
# Exit code 1 if a rule breaks or S4 averages over its budget. Uses: orchestrate.py, capture_api.py, stages_orchestrate.py.
import json
import random
import sys
import time
import uuid

sys.path.insert(0, ".")
from app.pipeline import capture_api, fakes, orchestrate, stages_orchestrate
from app.pipeline.adapters import make_memory_adapters, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.golden import NOW, SEED

# Config
DEFAULT_CHATS = 1000
REAL_PARTS = frozenset({"s3", "postgres", "valkey", "kafka"})
S4_BUDGET_SECONDS = 0.15  # the design budget for S4 per task, the same as S3's
CHAT = "conn_web_chat"
VISITS = ["I want a refund for my last order", "yes, that one", "please refund my other order too"]


def build_lane(real: bool, tag: str, timings: list[float]):
    """S1 to S4, in memory or on real infra; S4's consumer is timed and nothing runs after it."""
    seed = {**SEED, "tenant_id": f"volume_{tag}"} if real else SEED
    adapters = real_adapters(REAL_PARTS, topic_prefix=f"vol4{tag}.") if real else make_memory_adapters
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, adapters)
    lane.bus.subscribers = {topic: lane.bus.subscribers[topic][:1] for topic in ("signals.raw", "signals.normalized")}

    def timed_s4(envelope) -> None:
        started = time.perf_counter()
        stages_orchestrate.begin_run(lane, envelope)
        timings.append(time.perf_counter() - started)

    lane.bus.subscribe("tasks.created", "worker", "S4", timed_s4)
    return lane


def send(lane, chat_number: int, visit: int, text: str) -> None:
    """One chat message, captured the way the webhook does it."""
    body = json.dumps({"visitor_name": "Visitor", "visitor_email": f"visitor{chat_number}@example.lk", "text": text, "sent_at": "2026-10-10T09:55:00+05:30"}).encode()
    headers = {capture_api.EXTERNAL_ID_HEADER: f"vol_{chat_number}_{visit}", "session": f"sess_{chat_number}"}
    orchestrate.capture_signal(lane, capture_api.build_raw(CHAT, lane.seed["connectors"][CHAT], "application/json", body, headers))


def run_traffic(lane, chats: int) -> int:
    """Every chat asks, confirms, and a third of them ask again. Returns how many messages went in."""
    generator, sent = random.Random(2026), 0
    for chat_number in range(chats):
        for visit, text in enumerate(VISITS[: 3 if generator.random() < 0.33 else 2]):
            send(lane, chat_number, visit, text)
            lane.bus.drain()
            sent += 1
    return sent


def rules_hold(lane, chats: int) -> bool:
    """One run per chat, every task handled once, and every join points at its own chat's run."""
    started = {e.payload["run_id"]: e.payload["handoff"]["conversation_id"] for e in lane.bus.topics.get("runs.started", [])}
    joined = [e.payload for e in lane.bus.topics.get("runs.continued", [])]
    handled = sorted([e.payload["task_id"] for e in lane.bus.topics.get("runs.started", [])] + [j["task_id"] for j in joined])
    tasks = sorted(e.payload["task_id"] for e in lane.bus.topics.get("tasks.created", []))
    one_run_per_chat = len(started) == chats and len(set(started.values())) == chats
    return one_run_per_chat and handled == tasks and all(j["run_id"] in started for j in joined)


def main() -> int:
    # Step 1: build the lane
    chats = int(next((arg for arg in sys.argv[1:] if arg.isdigit()), DEFAULT_CHATS))
    real, tag, timings = "--real" in sys.argv, uuid.uuid4().hex[:8], []
    lane = build_lane(real, tag, timings)

    # Step 2: run the traffic, then check the rules and the speed
    try:
        sent = run_traffic(lane, chats)
        ok = rules_hold(lane, chats)
    finally:
        if real:
            delete_prefixed_topics(f"vol4{tag}.")
    per_task, slowest = sum(timings) / len(timings), sorted(timings)[int(len(timings) * 0.95)]
    print(f"chats {chats}, messages {sent}, S4 tasks {len(timings)}, runs {len(lane.bus.topics.get('runs.started', []))}, joins {len(lane.bus.topics.get('runs.continued', []))}")
    print(f"S4 {per_task * 1000:.2f} ms per task, p95 {slowest * 1000:.2f} ms, rules {'hold' if ok else 'BROKEN'}")
    return 0 if ok and per_task <= S4_BUDGET_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
