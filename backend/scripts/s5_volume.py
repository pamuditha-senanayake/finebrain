# s5_volume.py: the nightly volume run for S5. Fills the shop's real database with thousands of customers and orders,
# then asks S5 for many random customers, times and readers, the way S4's run does, and checks the rules still hold.
# Run from backend/:  uv run python scripts/s5_volume.py [customers] [--real]   (Postgres always: the shop lives there;
# --real also keeps the brain's knowledge, vault and records in Postgres). Exit code 1 if a rule breaks or S5 averages
# over its budget. Afterwards the sample shop is put back. Uses: retrieve_case.py, scripts/shop_db.py, tests/s5_world.py.
import random
import sys
import time
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, ".")
from app.pipeline import pii, run_steps, stages_orchestrate
from app.pipeline.adapters import real_adapters
from app.pipeline.contracts_reason import ContextQuery
from scripts import shop_db
from tests.golden import SEED
from tests.s5_world import ask, make_lane, world_seed

# Config
DEFAULT_CUSTOMERS = 2000
QUERIES = 1000
S5_BUDGET_SECONDS = 0.4  # the design budget for S5 (reference doc section 5)
START = datetime.fromisoformat("2025-01-01T09:00:00+05:30")
WINDOWS = {"item_policy_window_v1", "item_policy_window_v2", "item_policy_window", "item_policy_window_v4"}


def big_world(customers: int) -> dict:
    """Customers with 0 to 5 orders each over two years; some orders refunded."""
    generator = random.Random(2026)
    world = {"customers": [], "orders": [], "refunds": []}
    for number in range(customers):
        world["customers"].append({"id": f"cus_{number}", "email": f"c{number}@example.lk", "name": f"Customer {number}"})
        for order in range(generator.randint(0, 5)):
            paid = START + timedelta(days=generator.randint(0, 640), minutes=generator.randint(0, 1440))
            order_id = f"ORD-{number}-{order}"
            world["orders"].append({"id": order_id, "customer_id": f"cus_{number}", "product": "Item", "total_minor": generator.randint(1, 200) * 10000,
                                    "currency": "LKR", "status": "paid", "paid_at": paid.isoformat(), "payment_ref": f"pay_FB_{paid:%Y%m%d}_{number % 10000:04d}{order}"[:25]})
            if generator.random() < 0.2:
                world["refunds"].append({"id": f"RF-{order_id}", "order_id": order_id, "amount_minor": 10000, "status": "approved", "created_at": (paid + timedelta(days=3)).isoformat()})
    return world


def run_queries(lane, world: dict) -> tuple[list[float], list[bool]]:
    """Random customers, times and readers. Returns the timings and whether each answer kept the rules."""
    generator = random.Random(7)
    owner = {o["payment_ref"]: o for o in world["orders"]}
    principal = stages_orchestrate.principal_of(lane, "agent_refund_worker")
    timings, kept = [], []
    for number in range(QUERIES):
        customer = generator.choice(world["customers"])
        token = pii.make_token(lane.seed["tenant_id"], customer["email"])
        lane.vault[token] = customer["email"]  # what S2 does when the customer writes
        as_of = START + timedelta(days=generator.randint(0, 700))
        query = ContextQuery(run_id=f"vol_{number}", principal=principal, on_behalf_of=None, query_text=run_steps.QUERY_TEXT, branch="main",
                             node_types=["policy", "fact"], customer_ref=token, as_of_valid=as_of)
        started = time.perf_counter()
        bundle, _ = ask(lane, query)
        timings.append(time.perf_counter() - started)
        refs = [ref for item in bundle.items if item.item_id.startswith("order:") for ref in owner if ref in item.text]
        kept.append(all(owner[ref]["customer_id"] == customer["id"] and datetime.fromisoformat(owner[ref]["paid_at"]) <= as_of for ref in refs)
                    and len({item.item_id for item in bundle.items} & WINDOWS) <= 1)
    return timings, kept


def main() -> int:
    # Step 1: fill the shop's database and build the lane
    customers = int(next((arg for arg in sys.argv[1:] if arg.isdigit()), DEFAULT_CUSTOMERS))
    world = big_world(customers)
    shop_db.create_database()
    seed = {**world_seed(SEED), "tenant_id": f"test_{uuid.uuid4().hex[:8]}"} if "--real" in sys.argv else None
    lane = make_lane(real_adapters(frozenset({"postgres"})) if seed else None, seed=seed)
    shop_db.load_world(world)

    # Step 2: ask, then check the rules and the speed; put the sample shop back either way
    try:
        timings, kept = run_queries(lane, world)
    finally:
        shop_db.load_world()
    per_query, slowest = sum(timings) / len(timings), sorted(timings)[int(len(timings) * 0.95)]
    print(f"customers {customers}, orders {len(world['orders'])}, refunds {len(world['refunds'])}, S5 reads {len(timings)}, rules kept {sum(kept)}")
    print(f"S5 {per_query * 1000:.1f} ms per read, p95 {slowest * 1000:.1f} ms, rules {'hold' if all(kept) else 'BROKEN'}")
    return 0 if all(kept) and per_query <= S5_BUDGET_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
