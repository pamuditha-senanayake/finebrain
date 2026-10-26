# s7_s10_volume.py: the nightly volume run for S7, S8 and S10. Many customers of a big shop (real Postgres) each chat twice
# (a refund ask, then "yes") through the whole pipeline in-process, with a model that asks first and then proposes a
# refund of a random order. Rules: money moves only for the customer's own order when the policy allows it on its own
# (30 days, LKR 50,000, never refunded); others wait for a person or escalate; no payment is refunded twice; every run ends
# resolved, waiting for approval or escalated. Run from backend/:  uv run python scripts/s7_s10_volume.py [chats]
# Uses: orchestrate.py, scripts/s5_volume.py (big_world), scripts/shop_db.py, tests/s7_world.py, tests/s6_world.py.
import json
import random
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, ".")
from app.pipeline import fakes
from scripts import shop_db
from scripts.s5_volume import big_world
from tests.s7_world import full_lane, says

# Config
DEFAULT_CHATS = 300
BUDGET_SECONDS = 0.5  # S4 to S10 per chat, two turns, without a real model
WINDOW_DAYS, AUTO_LIMIT = 30, 5000000
NOW = datetime.fromisoformat("2026-10-10T10:00:00+05:30")


class NoLimit:
    """S9's rate limiter, lifted: this run measures S7, S8 and S10, not how fast S9 lets refunds out."""
    def allow(self, *args) -> bool:
        return True


def recent_world(customers: int) -> dict:
    """big_world, moved so most orders fall inside the window around the golden frozen time."""
    world = big_world(customers)
    for order in world["orders"]:
        paid = datetime.fromisoformat(order["paid_at"])
        order["paid_at"] = (NOW - timedelta(days=(NOW - paid).days % 60, hours=1)).isoformat()
    for refund in world["refunds"]:
        refund["created_at"] = NOW.isoformat()
    return world


def model_for(generator: random.Random, world: dict, customer: dict):
    """Asks first, then proposes a refund of one of the customer's orders (or, sometimes, someone else's), in full."""
    own = [o for o in world["orders"] if o["customer_id"] == customer["id"]] or world["orders"]
    order = generator.choice(own if generator.random() < 0.8 else world["orders"])
    left = order["total_minor"] - sum(r["amount_minor"] for r in world["refunds"] if r["order_id"] == order["id"])
    question = {"message_plain": "Which order?", "awaits_customer": True, "rationale_summary": "ask", "citations": ["item_policy_window"], "confidence": 0.9}
    refund = {"payment_ref": order["payment_ref"], "amount": {"amount_minor": max(left, 1), "currency": "LKR"}, "reason_code": "other",
              "rationale_summary": "refund", "citations": [f"order:{order['id']}", "item_policy_window"], "confidence": 0.9}
    replies = [fakes.tool_response("reply_customer", question)] + [fakes.tool_response("issue_refund", refund)] * 4
    return lambda system, messages, tools: replies.pop(0) if replies else fakes.text_response("done")


def allowed_on_its_own(order: dict, world: dict, customer: dict, paid_before: set) -> bool:
    refunded = sum(r["amount_minor"] for r in world["refunds"] if r["order_id"] == order["id"])
    days = (NOW - datetime.fromisoformat(order["paid_at"])).days
    return order["customer_id"] == customer["id"] and days <= WINDOW_DAYS and order["total_minor"] <= AUTO_LIMIT and refunded == 0 and order["payment_ref"] not in paid_before


def main() -> int:
    chats = int(next((arg for arg in sys.argv[1:] if arg.isdigit()), DEFAULT_CHATS))
    world = recent_world(max(chats, 200))
    lane = full_lane()
    lane.tooling.update(limiter=NoLimit(), sleep=lambda seconds: None)  # S9's 10 refunds a minute is S9's rule, tested on its own
    shop_db.load_world(world)
    generator, by_ref, paid, timings, broken, ends = random.Random(5), {o["payment_ref"]: o for o in world["orders"]}, set(), [], 0, {}
    try:
        for number in range(chats):
            customer = generator.choice(world["customers"])
            lane.model = model_for(generator, world, customer)
            who = {"email": customer["email"], "session": f"vol_{number}", "name": "Visitor"}
            before = len(lane.bus.topics.get("actions.executed", []))
            started = time.perf_counter()
            says(lane, {"id": f"v{number}a", "text": "I want a refund for my last order"}, **who)
            says(lane, {"id": f"v{number}b", "text": "yes, that one"}, **who)
            timings.append(time.perf_counter() - started)
            for result in lane.bus.topics.get("actions.executed", [])[before:]:
                if result.payload["tool_id"] != "tool_payment_refund" or result.payload["status"] != "succeeded":
                    continue
                trace = json.loads(lane.object_store[f"s3://brain/{lane.seed['tenant_id']}/traces/{result.payload['run_id']}.json"])
                order = by_ref[trace["action"]["arguments"]["payment_ref"]]
                broken += 0 if allowed_on_its_own(order, world, customer, paid) else 1
                paid.add(order["payment_ref"])
            end = lane.bus.topics["runs.completed"][-1].payload["outcome"]
            ends[end] = ends.get(end, 0) + 1
    finally:
        shop_db.load_world()
    slowest = sorted(timings)[int(len(timings) * 0.95)]
    print(f"chats {chats}, refunds paid {len(paid)}, run endings {ends}, rule breaks {broken}")
    print(f"S1 to S10 {sum(timings) / len(timings) * 1000:.1f} ms per chat (two turns), p95 {slowest * 1000:.1f} ms, rules {'hold' if not broken else 'BROKEN'}")
    return 0 if not broken and sum(timings) / len(timings) <= BUDGET_SECONDS and set(ends) <= {"resolved", "awaiting_approval", "escalated"} else 1


if __name__ == "__main__":
    sys.exit(main())
