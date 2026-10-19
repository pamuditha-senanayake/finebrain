# test_scope.py: step 13b, narrow first. A case's scope is its entities plus what typed links reach in two hops; S5 searches
# that slice (plus general knowledge) and widens only when it finds too little; facts count only for their own entities.
# Uses: app/pipeline/retrieve_scope.py, stages_retrieve.py, store_chunks*.py, api/ask.py, tests/golden.py, tests/test_entities.py.
import uuid

import pytest

from app.api import ask
from app.pipeline import fakes, observe, retrieve_scope, stages_retrieve, store_postgres
from app.pipeline.contracts_reason import ContextQuery
from app.pipeline.entity_match import entity_id_of
from app.pipeline.store_chunks import MemoryChunks
from app.pipeline.store_chunks_pg import PostgresChunks
from app.pipeline.store_entities import MemoryEntities
from tests.golden import NOW, SEED, scoped_query, tagged_knowledge
from tests.test_entities import make_lane, send

# Config
PAYMENT_A, PAYMENT_B = "pay_FB_20261004_0192", "pay_FB_20260830_0047"  # samples s2 and s3
ASKER = "head_of_cs"
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")


# --- Helpers

def ids(bundle) -> set[str]:
    return {item.item_id for item in bundle.items}


def retrieve_in(lane, query: ContextQuery):
    return stages_retrieve.retrieve(query, lane.chunks, lane.embed, lane.rerank, lane.seed["people"], lane.new_id, lane.now)[0]


def signal_of(lane, external_id: str) -> dict:
    return next(e.payload for e in lane.bus.topics["signals.normalized"] if e.payload["dedup_key"].endswith(f":{external_id}"))


# --- Building the scope

def test_links_reach_two_hops_and_no_further():
    store = MemoryEntities()
    chain = ["customer", "payment", "document", "other_payment"]  # customer paid with payment, a document mentions it and another payment
    for name in chain:
        store.note(name, "thing", name, "src", NOW)
    for left, right in zip(chain, chain[1:]):
        store.link(left, "linked", right, "src", NOW)
    assert retrieve_scope.linked(store, ["customer"]) == ["customer", "payment", "document"]
    assert retrieve_scope.linked(store, ["ent_unknown"]) == []


def test_a_customer_reaches_their_payment():
    lane = make_lane()
    send(lane, "s2", "mail_a")
    customer = entity_id_of("customer", signal_of(lane, "mail_a")["actor"]["ref"])
    assert retrieve_scope.linked(lane.entities, [customer]) == [customer, entity_id_of("payment", PAYMENT_A)]


def test_the_ladder_goes_from_narrow_to_wide():
    query = scoped_query("s2")
    assert [level for level, _ in retrieve_scope.ladder(query)] == ["entity", "domain", "tenant"]
    assert [level for level, _ in retrieve_scope.ladder(query.model_copy(update={"entity_ids": [], "domains": []}))] == ["tenant"]


# --- Searching inside it

def test_a_run_sees_its_own_payment_and_the_policies_never_another_customers():
    lane = make_lane()
    send(lane, "s2", "mail_a")
    send(lane, "s3", "mail_b")
    signal = signal_of(lane, "mail_a")
    query = scoped_query("s2").model_copy(update={"entity_ids": retrieve_scope.linked(lane.entities, signal["entity_ids"])})
    bundle = retrieve_in(lane, query)
    assert "item_payment_s2" in ids(bundle) and "item_payment_s3" not in ids(bundle) and "item_policy_window" in ids(bundle)
    assert bundle.scope.level == "entity" and bundle.scope.domains == ["customer_care"]


def test_too_little_in_the_scope_widens_and_says_so():
    lane = make_lane()
    observe.reset_counts()
    query = scoped_query("s2").model_copy(update={"domains": ["legal"], "entity_ids": ["ent_unknown"], "query_text": "refund window days"})
    bundle = retrieve_in(lane, query)
    assert bundle.scope.level == "tenant" and observe.read_count("s5.widened") == 2 and "item_policy_window" in ids(bundle)


def test_a_fact_counts_only_for_its_own_entities_even_when_widened():
    lane = make_lane()
    query = scoped_query("s2").model_copy(update={"entity_ids": [], "domains": []})
    assert not {"item_payment_s2", "item_payment_s3"} & ids(retrieve_in(lane, query))


def test_ask_narrows_to_the_payment_a_question_names():
    lane = make_lane()
    send(lane, "s2", "mail_a")
    named = ask.read_for(lane, ASKER, f"What was paid in {PAYMENT_A}?")
    assert named.scope.level == "entity" and "item_payment_s2" in ids(named) and "item_payment_s3" not in ids(named)
    assert ask.read_for(lane, ASKER, "How long is the refund window?").scope.level == "tenant"


# --- The same scope on both stores

def filled(chunks):
    knowledge = tagged_knowledge() + [{**tagged_knowledge()[0], "item_id": "legal_note", "text": "Refund law note.", "domain": "legal", "entity_ids": []}]
    for item, vector in zip(knowledge, fakes.fake_embed([item["text"] for item in knowledge])):
        chunks.add(item, vector)
    return chunks


def scoped_hits(chunks) -> set[str]:
    scope = {"domains": ["customer_care"], "entity_ids": [entity_id_of("payment", PAYMENT_A)]}
    kinds = ["policy", "fact", "chunk"]
    return {item["item_id"] for item in chunks.by_text("refund payment LKR law", kinds, NOW, NOW, 50, scope)}


def test_memory_scope_keeps_general_and_own_items_only():
    found = scoped_hits(filled(MemoryChunks()))
    assert "item_payment_s2" in found and "item_policy_window" in found and not {"item_payment_s3", "legal_note"} & found


@NEEDS_POSTGRES
def test_postgres_scope_gives_the_same_answer():
    chunks = filled(PostgresChunks(store_postgres.connect(), f"test_scope_{uuid.uuid4().hex[:8]}"))
    assert scoped_hits(chunks) == scoped_hits(filled(MemoryChunks()))
