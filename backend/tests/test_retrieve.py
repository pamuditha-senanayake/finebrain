# test_retrieve.py: S5 step 7 (hybrid search, as-of time, access, budget) and step 8 (degraded search, skipped rerank,
# unavailable store, and S4's one retry then escalate). Uses: stages_retrieve.py, store_chunks.py, orchestrate.py, tests/golden.py.
import uuid
from datetime import datetime

import pytest

from app.pipeline import fakes, observe, orchestrate, stages_retrieve
from app.pipeline.contracts_reason import ContextQuery
from app.pipeline.store_chunks import MemoryChunks, PostgresChunks
from app.pipeline.store_postgres import connect, database_is_up
from tests.golden import NOW, RAW, SEED, golden, recorded_answers

# Config
S2_QUERY = ContextQuery.model_validate(golden("s2", "ContextQuery"))
REFUND_CITATIONS = set(golden("s2", "ProposedAction")["citations"])


# --- Helpers

def fill(chunks):
    for item, vector in zip(SEED["knowledge"], fakes.fake_embed([item["text"] for item in SEED["knowledge"]])):
        chunks.add(item, vector)
    return chunks


def retrieve(query: ContextQuery = S2_QUERY, chunks=None, embed=fakes.fake_embed, rerank=fakes.fake_rerank):
    bundle, _ = stages_retrieve.retrieve(query, chunks or fill(MemoryChunks()), embed, rerank, SEED["people"], fakes.make_id_maker(), NOW)
    return bundle


def ids(bundle) -> set[str]:
    return {item.item_id for item in bundle.items}


def broken(*args, **kwargs):
    raise ConnectionError("service down")


# --- Step 7

def test_hybrid_search_finds_the_policies_and_this_payment_only():
    found = ids(retrieve())
    assert REFUND_CITATIONS <= found and "item_payment_s3" not in found  # another customer's payment never shows


def test_expired_policy_is_left_out_today_but_found_as_of_last_year():
    assert "item_policy_window_v2" not in ids(retrieve())
    last_year = datetime.fromisoformat("2025-06-01T00:00:00+05:30")
    past = ids(retrieve(S2_QUERY.model_copy(update={"as_of_valid": last_year, "as_of_recorded": last_year})))
    assert "item_policy_window_v2" in past and "item_policy_window" not in past


def test_facts_not_yet_known_at_the_recorded_time_are_left_out():
    before_payment = datetime.fromisoformat("2026-10-01T00:00:00+05:30")
    assert "item_payment_s2" not in ids(retrieve(S2_QUERY.model_copy(update={"as_of_recorded": before_payment})))


@pytest.mark.parametrize("person, sees_payment", [("head_of_cs", True), ("support_operator_1", True), ("someone_unknown", False)])
def test_on_behalf_of_sees_only_what_both_may(person, sees_payment):
    bundle = retrieve(S2_QUERY.model_copy(update={"on_behalf_of": person}))
    assert ("item_payment_s2" in ids(bundle)) is sees_payment
    assert bundle.denied_count == (0 if sees_payment else 4)


def test_token_budget_trims_the_bundle():
    assert len(retrieve(S2_QUERY.model_copy(update={"max_tokens": 20})).items) == 1


# --- Step 8

def test_embedding_outage_degrades_to_exact_words():
    observe.reset_counts()
    assert REFUND_CITATIONS <= ids(retrieve(embed=broken)) and observe.read_count("s5.degraded") == 1


def test_rerank_outage_keeps_the_fused_order():
    observe.reset_counts()
    assert REFUND_CITATIONS <= ids(retrieve(rerank=broken)) and observe.read_count("s5.rerank_skipped") == 1


def test_unreadable_store_is_context_unavailable():
    class BrokenChunks:
        by_text = by_vector = staticmethod(broken)

    with pytest.raises(stages_retrieve.ContextUnavailable) as raised:
        retrieve(chunks=BrokenChunks())
    assert raised.value.retryable is True


def test_s4_retries_once_then_escalates_without_acting():
    # Step 1: a lane whose knowledge store is down
    gateway, paid = fakes.make_fake_gateway()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], gateway, NOW)
    calls = []

    def down(*args, **kwargs):
        calls.append(1)
        raise ConnectionError("database down")

    lane.chunks.by_text = down

    # Step 2: the refund email arrives
    orchestrate.capture_signal(lane, RAW["s2_refund_monthly_in_policy"])
    lane.bus.drain()
    run = lane.bus.topics["runs.completed"][-1].payload
    assert (run["outcome"], run["steps"][0]["decision"], len(calls)) == ("escalated", "context_unavailable", 2)
    assert paid == {} and "actions.executed" not in lane.bus.topics


def test_retrieval_and_governance_both_log_access_decisions():
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    first = orchestrate.capture_signal(lane, RAW["s2_refund_monthly_in_policy"])
    lane.bus.drain()
    decisions = lane.bus.topics["access.decisions"]
    assert [envelope.producer for envelope in decisions] == ["internal", "governance"]  # S5 read, then S7 act
    assert {envelope.correlation_id for envelope in decisions} == {first.correlation_id}


@pytest.mark.skipif(not database_is_up(), reason="no Postgres on localhost:5433")
def test_postgres_chunks_give_the_same_answer():
    chunks = fill(PostgresChunks(connect(), f"test_{uuid.uuid4().hex[:8]}"))
    found = ids(retrieve(chunks=chunks))
    assert REFUND_CITATIONS <= found and "item_payment_s3" not in found and "item_policy_window_v2" not in found
