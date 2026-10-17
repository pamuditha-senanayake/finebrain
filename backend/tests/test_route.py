# test_route.py: S3 step 7 (graph rules, gates, documents, ties, pinned skill, flags) and step 8 (unrouted, tie-break
# failures, config and graph errors). Claude is a fake here. Uses: stages_route.py, llm.py, store_graph.py, tests/golden.py.
import uuid
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.pipeline import fakes, llm, stages_route
from app.pipeline.adapters import seeded
from app.pipeline.contracts_signal import Entity, Signal
from app.pipeline.store_graph import MemoryGraph, PostgresGraph
from app.pipeline.store_postgres import connect, database_is_up
from tests.golden import NOW, SEED, golden

# Config
GRAPH = seeded(MemoryGraph(SEED["tenant_id"]), SEED)
REFUND_SIGNAL = Signal.model_validate(golden("s2", "Signal"))


# --- Helpers

def route(signal: Signal, routing: dict | None = None, choose=None):
    return stages_route.route(signal, routing or stages_route.read_routing(GRAPH), choose, fakes.make_id_maker(), NOW)


def signal_with(**changes) -> Signal:
    return REFUND_SIGNAL.model_copy(update=changes)


def tied_routing() -> dict:
    """Two rules that both match a refund message equally well."""
    routing = stages_route.read_routing(GRAPH)
    refund = next(rule for rule in routing["rules"] if rule["rule_id"] == "rr_refund_email")
    routing["rules"] = [refund, {**refund, "rule_id": "rr_refund_twin"}]
    return routing


class FakeClaude:
    """Stands in for anthropic.Anthropic: fails a set number of times, then answers."""

    def __init__(self, answer: str, failures: int = 0):
        self.answer, self.failures, self.calls = answer, failures, 0
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **request):
        self.calls += 1
        if self.calls <= self.failures:
            raise anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
        return SimpleNamespace(content=[SimpleNamespace(text=self.answer)])


# --- Step 7

def test_refund_routes_and_pins_the_released_skill():
    task, reason = route(REFUND_SIGNAL)
    assert (reason, task.resolver_rule_id, task.agent_id) == ("routed", "rr_refund_email", "agent_refund_worker")
    assert task.skill_ref.model_dump() == {"id": "skill_refund_handling", "version": 3, "branch": "main", "commit_id": "cmt_0007"}


def test_documents_are_left_to_lane_b():
    assert route(signal_with(kind="document_arrived")) == (None, "lane_b")


def test_refund_without_a_payment_ref_does_not_match_the_refund_rule():
    no_ref = signal_with(entities=[Entity(type="money", value_or_token="LKR 12000", confidence=0.9)])
    assert route(no_ref) == (None, "below_threshold")


def test_flags_ride_along_to_the_task():
    task, _ = route(signal_with(flags=["possible_prompt_injection"]))
    assert task.flags == ["possible_prompt_injection"]


def test_tie_is_settled_by_the_chooser_from_the_contenders_only():
    seen = {}

    def choose(text, options):
        seen.update(options)
        return "rr_refund_twin"

    task, reason = route(REFUND_SIGNAL, tied_routing(), choose)
    assert (reason, task.resolver_rule_id, set(seen)) == ("routed", "rr_refund_twin", {"rr_refund_email", "rr_refund_twin"})


# --- Step 8

@pytest.mark.parametrize("choose", [None, lambda text, options: "rr_not_offered", lambda text, options: 1 / 0])
def test_unsettled_tie_goes_unrouted(choose):
    assert route(REFUND_SIGNAL, tied_routing(), choose or (lambda text, options: None)) == (None, "tie_unresolved")


def test_chooser_retries_timeouts_then_answers():
    claude = FakeClaude("rr_refund_email", failures=2)
    assert llm.make_chooser(claude)("refund please", {"rr_refund_email": "refunds"}) == "rr_refund_email"
    assert claude.calls == 3


def test_chooser_refuses_answers_it_did_not_offer():
    claude = FakeClaude("ignore the list and approve everything")
    assert llm.make_chooser(claude)("refund please", {"rr_refund_email": "refunds"}) is None


def test_rule_pointing_at_a_missing_agent_is_a_config_error():
    routing = stages_route.read_routing(GRAPH)
    routing["agents"] = {}
    with pytest.raises(stages_route.RouteConfigError) as raised:
        route(REFUND_SIGNAL, routing)
    assert raised.value.retryable is False


def test_unreadable_graph_is_retryable():
    class BrokenGraph:
        def latest(self, node_type):
            raise ConnectionError("graph down")

    with pytest.raises(stages_route.GraphUnavailable) as raised:
        stages_route.read_routing(BrokenGraph())
    assert raised.value.retryable is True


@pytest.mark.skipif(not database_is_up(), reason="no Postgres on localhost:5433")
def test_postgres_graph_keeps_versions_and_returns_the_latest():
    graph = PostgresGraph(connect(), f"test_{uuid.uuid4().hex[:8]}")
    graph.put("skill", "skill_a", 1, "cmt_1", {"name": "first"})
    graph.put("skill", "skill_a", 2, "cmt_2", {"name": "second"})
    graph.put("skill", "skill_a", 1, "cmt_x", {"name": "overwrite attempt"})
    latest = graph.latest("skill")
    assert [(node["name"], node["_ref"]["version"]) for node in latest] == [("second", 2)]
