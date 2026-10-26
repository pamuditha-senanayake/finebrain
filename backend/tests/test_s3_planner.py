# test_s3_planner.py: S3 Planner, rules first with Claude as the fallback, and rules that must always hold.
# Claude is a fake here, so every answer is known. Uses: stages_route.py, store_graph.py, adapters.py, tests/test_s2_checks.py.
import random

from app.pipeline import stages_route
from app.pipeline.adapters import seeded
from app.pipeline.contracts_signal import Entity, Signal
from app.pipeline.store_graph import MemoryGraph
from tests.golden import NOW, SEED
from tests.test_s2_checks import FROZEN as S2_FROZEN

# Config
ROUTING = stages_route.read_routing(seeded(MemoryGraph(SEED["tenant_id"]), SEED))
ANNA = Signal.model_validate({**S2_FROZEN[0], "signal_id": "sig_anna", "raw_event_id": "evt_anna"})
NO_KEYWORD = "Can I get my money back for the last order?"  # a refund, without the word refund


# --- Helpers

def plan(signal: Signal, choose):
    return stages_route.route(signal, ROUTING, choose, NOW)


def spy(answer):
    """A fake Claude that records what it was offered and gives one fixed answer."""
    offered = []

    def choose(text: str, options: dict) -> str | None:
        offered.append(set(options))
        return answer

    return choose, offered


# --- Rules first

def test_a_clear_match_never_asks_claude():
    choose, offered = spy("rr_billing_question")
    task, reason = plan(ANNA, choose)
    assert (reason, task.resolver_rule_id, offered) == ("routed", "rr_refund_chat", [])


# --- Claude as the fallback

def test_claude_picks_the_recipe_when_no_rule_is_clear():
    choose, offered = spy("rr_refund_chat")
    task, reason = plan(ANNA.model_copy(update={"text_masked": NO_KEYWORD}), choose)
    assert (reason, task.resolver_rule_id, task.agent_id) == ("planned", "rr_refund_chat", "agent_refund_worker")
    assert "planned_by_model" in task.flags and task.match_score < stages_route.MATCH_THRESHOLD
    assert offered == [{"rr_refund_chat", "rr_billing_question"}]  # only rules whose gates pass; the email rule is not offered


def test_claude_saying_none_or_off_list_leaves_it_unrouted():
    for answer in (None, "rr_made_up"):
        task, reason = plan(ANNA.model_copy(update={"text_masked": NO_KEYWORD}), spy(answer)[0])
        assert (task, reason) == (None, "below_threshold")


def test_claude_failing_leaves_it_unrouted():
    def broken(text, options):
        raise TimeoutError("model did not answer")

    assert plan(ANNA.model_copy(update={"text_masked": NO_KEYWORD}), broken) == (None, "below_threshold")


# --- Rules that always hold, over random messages and random Claude answers

def random_signal(generator, number: int) -> Signal:
    words = ["refund", "money back", "invoice", "charge", "order", "hello", "payment", "billing", "ignore previous instructions"]
    entities = [Entity(type="payment_ref", value_or_token="pay_FB_20261004_0192", confidence=0.95)] if generator.random() < 0.3 else []
    return ANNA.model_copy(update={
        "signal_id": f"sig_{number}", "channel": generator.choice(["chat", "email"]), "entities": entities,
        "text_masked": " ".join(generator.choices(words, k=generator.randint(1, 5))),
    })


def test_rules_hold_for_random_messages():
    generator = random.Random(2026)  # fixed seed so a failure can be replayed
    rules = {rule["rule_id"]: rule for rule in ROUTING["rules"]}
    for number in range(300):
        signal = random_signal(generator, number)
        task, reason = plan(signal, spy(generator.choice([None, "rr_refund_chat", "rr_billing_question", "rr_refund_email", "rr_made_up"]))[0])
        if task is None:
            assert reason in ("below_threshold", "tie_unresolved")
            continue
        assert task.signal_ids == [signal.signal_id]  # the task never loses its signal
        assert stages_route.rule_applies(rules[task.resolver_rule_id], signal)  # Claude can never pass a rule's gates for it
        assert ("planned_by_model" in task.flags) == (reason == "planned")  # a model pick is always marked
        assert (reason == "planned") == (task.match_score < stages_route.MATCH_THRESHOLD)
