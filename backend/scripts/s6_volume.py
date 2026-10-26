# s6_volume.py: the nightly volume run for S6's checks. Thousands of turns over a big shop (real Postgres): S5 builds each
# customer's bundle, then a stand-in model proposes random refunds (anyone's payment, any amount, asked first or not) and
# S6 decides. Every refund S6 lets through must be that customer's own order, cited, within what is left, and confirmed in
# the chat. Run from backend/:  uv run python scripts/s6_volume.py [customers]. Exit code 1 if a rule breaks or S6's own
# work (without the model) averages over budget. Afterwards the sample shop is put back. Uses: stages_reason.py, scripts/s5_volume.py.
import random
import sys
import time

sys.path.insert(0, ".")
from app.pipeline import fakes, pii, retrieve_case, run_steps, stages_orchestrate, stages_reason
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.contracts_reason import ContextQuery
from scripts import shop_db
from scripts.s5_volume import big_world
from tests.s5_world import make_lane

# Config
DEFAULT_CUSTOMERS = 1000
TURNS = 2000
S6_CHECK_BUDGET_SECONDS = 0.05  # S6's own checks and prompt building; the model's time is S6's model budget, apart
SKILL = {"name": "Refund handling", "allowed_tools": ["issue_refund", "reply_customer", "escalate"], "steps": ["Refund an order the customer confirmed."]}


def random_refund(generator: random.Random, world: dict, own: list[dict]) -> object:
    order = generator.choice(own if own and generator.random() < 0.7 else world["orders"])
    amount = generator.choice([order["total_minor"], 10000, order["total_minor"] + 100])
    citations = generator.choice([[f"order:{order['id']}"], ["item_policy_window"]])
    return fakes.tool_response("issue_refund", {"payment_ref": order["payment_ref"], "amount": {"amount_minor": amount, "currency": "LKR"}, "reason_code": "other",
                                                "rationale_summary": "volume", "citations": citations, "confidence": 0.9})


def run_turns(lane, world: dict) -> tuple[list[float], list[bool], int]:
    """Random turns; returns S6 timings, whether each kept the rules, and how many refunds went through."""
    generator, principal = random.Random(11), stages_orchestrate.principal_of(lane, "agent_refund_worker")
    task = TaskRequest.model_validate({"task_id": "task_vol", "signal_ids": ["sig_vol"], "activity_id": "act_refund_request", "agent_id": "agent_refund_worker",
                                                 "skill_ref": {"id": "skill_refund_handling", "version": 3, "branch": "main", "commit_id": "cmt_0007"}, "on_behalf_of": None,
                                                 "resolver_rule_id": "rr_refund_chat", "match_score": 1.0, "base_criticality": 0, "due_at": lane.now, "priority": 3})
    timings, kept, through = [], [], 0
    for number in range(TURNS):
        customer = generator.choice(world["customers"])
        token = pii.make_token(lane.seed["tenant_id"], customer["email"])
        lane.vault[token] = customer["email"]
        query = ContextQuery(run_id=f"v{number}", principal=principal, on_behalf_of=None, query_text=run_steps.QUERY_TEXT, branch="main", node_types=["policy", "fact"], customer_ref=token)
        bundle, _ = retrieve_case.retrieve_for_run(lane, query)
        own = [o for o in world["orders"] if o["customer_id"] == customer["id"]]
        replies = [random_refund(generator, world, own) for _ in range(3)]
        previous = [{"signal_id": "x", "action_type": "reply_customer", "arguments": {"awaits_customer": True}}] if generator.random() < 0.5 else []
        started = time.perf_counter()
        action = stages_reason.propose(task, bundle, "refund please", SKILL, lambda s, m, t: replies.pop(0), f"v{number}", "step_04", "cc", previous=previous)
        timings.append(time.perf_counter() - started)
        if action.action_type == "issue_refund":
            through += 1
            order = next((o for o in world["orders"] if o["payment_ref"] == action.arguments["payment_ref"]), None)
            left = order["total_minor"] - sum(r["amount_minor"] for r in world["refunds"] if r["order_id"] == order["id"]) if order else -1
            kept.append(order is not None and order["customer_id"] == customer["id"] and action.money.amount_minor <= left and f"order:{order['id']}" in action.citations)
        else:
            kept.append(True)
    return timings, kept, through


def main() -> int:
    customers = int(next((arg for arg in sys.argv[1:] if arg.isdigit()), DEFAULT_CUSTOMERS))
    world = big_world(customers)
    lane = make_lane()
    shop_db.load_world(world)
    try:
        timings, kept, through = run_turns(lane, world)
    finally:
        shop_db.load_world()
    per_turn, slowest = sum(timings) / len(timings), sorted(timings)[int(len(timings) * 0.95)]
    print(f"customers {customers}, orders {len(world['orders'])}, S6 turns {len(timings)}, refunds let through {through}, refused or asked {len(timings) - through}")
    print(f"S6 checks {per_turn * 1000:.2f} ms per turn, p95 {slowest * 1000:.2f} ms, rules {'hold' if all(kept) else 'BROKEN'}")
    return 0 if all(kept) and per_turn <= S6_CHECK_BUDGET_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
