# s3_volume.py: the nightly volume run for S3. Routes many chat signals the way the S3 consumer does, reading the
# graph each time, and checks the rules still hold. Run from backend/:  uv run python scripts/s3_volume.py [count] [--real]
# --real reads the graph from Postgres (Docker). Exit code 1 if a rule breaks or S3 averages over its budget.
# Uses: stages_route.py, store_graph.py, store_postgres.py, adapters.py, tests/test_s3_planner.py (Anna's signal).
import random
import sys
import time
import uuid

sys.path.insert(0, ".")
from app.pipeline import stages_route, store_postgres
from app.pipeline.adapters import seeded
from app.pipeline.store_graph import MemoryGraph, PostgresGraph
from tests.golden import NOW, SEED
from tests.test_s3_planner import ANNA

# Config
DEFAULT_COUNT = 5000
S3_BUDGET_SECONDS = 0.15  # the design budget for S3 per signal
TEXTS = {  # what each kind of message must become, with no model in the loop
    "I want a refund for my last order": "rr_refund_chat",
    "billing: why is there a charge on my invoice": "rr_billing_question",
    "why is there a charge on my invoice": None,  # 2 of 3 billing keywords is below the threshold; the model would plan it
    "hello, is anyone there": None,
}


def build_graph(real: bool):
    """The routing graph, in memory or in Postgres under a throwaway tenant."""
    if not real:
        return seeded(MemoryGraph(SEED["tenant_id"]), SEED)
    tenant = f"test_{uuid.uuid4().hex[:8]}"  # conftest-style name, so clean_test_tenants removes it
    return seeded(PostgresGraph(store_postgres.connect(), tenant), {**SEED, "tenant_id": tenant})


def route_traffic(graph, count: int) -> tuple[list[float], list[bool]]:
    """Route every signal like the S3 consumer, timing each one. Returns times and whether each landed right."""
    generator = random.Random(2026)
    timings, correct = [], []
    for number in range(count):
        text = generator.choice(list(TEXTS))
        signal = ANNA.model_copy(update={"signal_id": f"sig_{number}", "text_masked": text})
        started = time.perf_counter()
        task, _ = stages_route.route(signal, stages_route.read_routing(graph), None, NOW)
        timings.append(time.perf_counter() - started)
        correct.append((task.resolver_rule_id if task else None) == TEXTS[text] and (task is None or task.signal_ids == [signal.signal_id]))
    return timings, correct


def main() -> int:
    # Step 1: build the graph
    count = int(next((arg for arg in sys.argv[1:] if arg.isdigit()), DEFAULT_COUNT))
    graph = build_graph("--real" in sys.argv)

    # Step 2: route the traffic
    timings, correct = route_traffic(graph, count)

    # Step 3: check the rules and the speed
    per_signal, slowest = sum(timings) / count, sorted(timings)[int(count * 0.95)]
    rules_hold = all(correct)
    print(f"routed {count}, landed right {sum(correct)}, wrong {count - sum(correct)}")
    print(f"S3 {per_signal * 1000:.2f} ms per signal, p95 {slowest * 1000:.2f} ms, rules {'hold' if rules_hold else 'BROKEN'}")
    return 0 if rules_hold and per_signal <= S3_BUDGET_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
