# s9_volume.py: the volume run for S9's refund tool on the real shop database. A big shop (thousands of orders) gets
# thousands of refund calls from many workers at once: full and partial refunds, retries of a key already used, two runs on
# the same order, wrong currencies, unknown payments, amounts over what was paid, other customers' orders. Rules checked in
# the shop afterwards: no order ever returns more than was paid, no customer is refunded someone else's order, one row per key and a retry gets the same row, every success has its row and no
# failure left one, each touched order's status matches its refunds, and every call got an answer.
# Run from backend/:  uv run python scripts/s9_volume.py [calls]   Uses: tools_write.py, scripts/s5_volume.py, scripts/shop_db.py, tests/s7_world.py.
import random
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import psycopg

sys.path.insert(0, ".")
from app.pipeline import tools_write
from scripts import shop_db
from scripts.s5_volume import big_world
from tests.s7_world import full_lane

# Config
DEFAULT_CALLS = 3000
CUSTOMERS = 1500  # about 3,700 orders: payment refs stay unique below 10,000
WORKERS = 8
BUDGET_P95_SECONDS = 0.15  # one refund: sign in, lock, check, write, commit, on a local Postgres
ANSWERS = {"succeeded", "exceeds_paid", "order_not_refundable", "currency_mismatch", "order_not_found", "shop_unavailable"}


def make_calls(world: dict, count: int) -> list[dict]:
    """Realistic refund calls, with about one in ten a retry of an earlier key."""
    generator, calls = random.Random(9), []
    emails = {c["id"]: c["email"] for c in world["customers"]}
    for number in range(count):
        if calls and generator.random() < 0.1:
            calls.append(dict(generator.choice(calls)))
            continue
        order = generator.choice(world["orders"])
        amount = generator.choice([order["total_minor"], order["total_minor"] // 2, order["total_minor"] + 1, 10000])
        currency = "USD" if generator.random() < 0.03 else "LKR"
        ref = "pay_FB_20990101_9999" if generator.random() < 0.02 else order["payment_ref"]
        owner = generator.choice(world["customers"])["email"] if generator.random() < 0.03 else emails[order["customer_id"]]  # some ask for another's order
        calls.append({"key": f"vol:run_{number}:step_1", "payment_ref": ref, "amount": {"amount_minor": amount, "currency": currency}, "customer": owner})
    return calls


def call_tool(lane, connection, call: dict) -> tuple[dict, dict, float]:
    started = time.perf_counter()
    answer = tools_write.refund(lane, connection, {"payment_ref": call["payment_ref"], "amount": call["amount"], "reason_code": "other"}, call["key"], call["customer"])
    return call, answer, time.perf_counter() - started


def broken_rules(results: list, world: dict) -> list[str]:
    """Every rule the shop's data breaks after the run. Empty means all held."""
    with psycopg.connect(shop_db.owner_url()) as db:
        rows = {rid: (order, amount) for rid, order, amount in db.execute("SELECT id, order_id, amount_minor FROM shop.refunds WHERE id LIKE 'RF-B-%'")}
        sums = dict(db.execute("SELECT order_id, sum(amount_minor) FROM shop.refunds WHERE status <> 'denied' GROUP BY 1").fetchall())
        status = dict(db.execute("SELECT id, status FROM shop.orders").fetchall())
    total = {o["id"]: o["total_minor"] for o in world["orders"]}
    broken = [f"{o} refunded {sums[o]} of {total[o]}" for o in sums if sums[o] > total[o]]
    by_key: dict[str, set] = {}
    for call, answer, _ in results:
        rid = tools_write.refund_id(call["key"])
        by_key.setdefault(call["key"], set()).add(answer["external_ref"] if answer["status"] == "succeeded" else None)
        if answer["status"] == "succeeded" and rid not in rows:
            broken.append(f"{call['key']} succeeded with no row")
        if (answer.get("error") or {}).get("code", "succeeded") not in ANSWERS:
            broken.append(f"{call['key']} answered {answer}")
    broken += [f"{key} got {refs}" for key, refs in by_key.items() if len(refs - {None}) > 1]
    owner_of, emails = {o["payment_ref"]: o["customer_id"] for o in world["orders"]}, {c["email"]: c["id"] for c in world["customers"]}
    broken += [f"{call['key']} refunded another customer's order" for call, answer, _ in results
               if answer["status"] == "succeeded" and owner_of.get(call["payment_ref"]) != emails[call["customer"]]]
    touched = {order for order, _ in rows.values()}
    broken += [f"{o} is {status[o]} with {sums[o]} of {total[o]}" for o in touched if status[o] != ("refunded" if sums[o] >= total[o] else "partially_refunded")]
    return broken


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CALLS
    world = big_world(CUSTOMERS)
    lane = full_lane()  # the sample shop, connected with both users
    shop_db.load_world(world)  # then the big shop in its place
    connection = tools_write.refunds_connection(lane)
    calls = make_calls(world, count)
    started = time.perf_counter()
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda call: call_tool(lane, connection, call), calls))
    wall = time.perf_counter() - started
    timings = sorted(seconds for _, _, seconds in results)
    p95 = timings[int(len(timings) * 0.95)]
    outcomes = Counter(a["status"] if a["status"] == "succeeded" else a["error"]["code"] for _, a, _ in results)
    broken = broken_rules(results, world)
    print(f"{count} refund calls, {WORKERS} workers, {len(world['orders'])} orders, {wall:.1f} s wall")
    print(f"answers: {dict(outcomes)}")
    print(f"per call: p50 {statistics.median(timings) * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms (budget {BUDGET_P95_SECONDS * 1000:.0f} ms)")
    print("rules: all held" if not broken else f"rules broken: {len(broken)}, e.g. {broken[:5]}")
    shop_db.setup()  # leave the sample shop as the tests expect it
    sys.exit(1 if broken or p95 > BUDGET_P95_SECONDS else 0)
