# activity_volume.py: the volume run for activities built in Workflow Studio. Landing page chat is built through Studio's
# API (sensor on the Landing chat connection, owner, policy, one skill, live); then thousands of realistic messages go
# through the real S1 to S3: visitors on the landing chat (questions, demo asks, pricing, refund words) and customers on
# the web chat. Rules checked: every landing message reaches Landing page chat with its owner and skill, no other message
# does, and each S3 route stays inside its budget. Run from backend/:  uv run python scripts/activity_volume.py [count] [--real]
# --real builds it on Postgres, Valkey and S3 under a throwaway tenant. Uses: tests/activity_world.py, tests/test_s5_real.py.
import random
import statistics
import sys
import time
import uuid

sys.path.insert(0, ".")
from app.pipeline.adapters import real_adapters
from tests.activity_world import build, build_landing, visitor
from tests.s5_world import visitor_says

# Config
DEFAULT_COUNT = 2000
BUDGET_SECONDS = 0.15  # S1 to S3 per message, the S3 design budget
LANDING_TEXTS = ["How much is the Agent Gateway?", "Can I see a demo?", "Do you offer a discount for startups?", "I want a refund for my payment",
                 "We would like to partner with you", "hello"]
WEB_TEXTS = ["I want a refund for my last order", "billing: why is there a charge on my invoice"]


def send_all(lane, count: int) -> tuple[list[tuple[str, dict | None]], list[float]]:
    """Random messages on both chats. Returns (which chat, the task S3 made or None) and each message's time."""
    generator, sent, timings = random.Random(11), [], []
    for number in range(count):
        before = len(lane.bus.topics.get("tasks.created", []))
        started = time.perf_counter()
        if generator.random() < 0.6:
            visitor(lane, generator.choice(LANDING_TEXTS), conversation=f"c-vol-{number}")
            where = "landing"
        else:
            visitor_says(lane, {"id": f"vol_web_{number}", "text": generator.choice(WEB_TEXTS)}, email=f"c{number}@example.lk", session=f"vol_{number}", name="Visitor")
            where = "web"
        timings.append(time.perf_counter() - started)
        created = lane.bus.topics.get("tasks.created", [])
        sent.append((where, created[-1].payload if len(created) > before else None))
    return sent, timings


def broken(sent: list[tuple[str, dict | None]], ids: dict) -> list[str]:
    wrong = []
    for number, (where, task) in enumerate(sent):
        on_landing = task is not None and task["activity_id"] == "landing_page_chat"
        if where == "landing" and not (on_landing and task["agent_id"] == ids["agent"] and task["skill_ref"]["id"] == ids["skill"]):
            wrong.append(f"landing message {number} went to {task and task['activity_id']}")
        if where == "web" and on_landing:
            wrong.append(f"web message {number} went to Landing page chat")
    return wrong


if __name__ == "__main__":
    count = int(next((a for a in sys.argv[1:] if a.isdigit()), DEFAULT_COUNT))
    real = "--real" in sys.argv
    adapters = real_adapters(frozenset({"postgres", "valkey", "s3"})) if real else None
    client, lane = build(adapters, tenant=f"vol_act_{uuid.uuid4().hex[:8]}" if real else None)
    lane.bus.subscribers.pop("tasks.created")  # S1 to S3 only: the routing is what is measured
    ids = build_landing(client, lane)
    sent, timings = send_all(lane, count)
    wrong = broken(sent, ids)
    landing = sum(1 for where, _ in sent if where == "landing")
    p95 = sorted(timings)[int(len(timings) * 0.95)]
    print(f"{count} messages ({landing} on the landing chat, {count - landing} on the web chat), graph {'Postgres' if real else 'memory'}")
    print(f"S1 to S3 per message: mean {statistics.mean(timings) * 1000:.1f} ms, p95 {p95 * 1000:.1f} ms (budget {BUDGET_SECONDS * 1000:.0f} ms)")
    print("rules: all held" if not wrong else f"rules broken: {len(wrong)}, e.g. {wrong[:3]}")
    sys.exit(1 if wrong or p95 > BUDGET_SECONDS else 0)
