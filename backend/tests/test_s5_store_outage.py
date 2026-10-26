# test_s5_store_outage.py: knowledge never goes missing because the embedding service refused at startup. The items are
# stored by their words, S5 still finds every policy, and the next start gives them their vectors. In memory and on the
# real Postgres index. Uses: store_chunks.py (load_chunks), store_chunks_pg.py, stages_retrieve.py, adapters.py, tests/golden.py.
import uuid

import pytest

from app.pipeline import fakes, observe, stages_retrieve, store_postgres
from app.pipeline.adapters import seeded
from app.pipeline.store_chunks import MemoryChunks, load_chunks
from app.pipeline.store_chunks_pg import PostgresChunks
from app.pipeline.store_graph import MemoryGraph
from tests.golden import NOW, SEED, scoped_query

# Config
POLICIES = {"item_policy_window", "item_policy_auto_limit", "item_policy_late_large"}


def refusing_embed(texts, kind):
    raise ConnectionError("embedding service refused")


def search(chunks, embed) -> set[str]:
    bundle, _ = stages_retrieve.retrieve(scoped_query("s2"), chunks, embed, lambda query, docs: [0.0] * len(docs), SEED["people"], fakes.make_id_maker(), NOW)
    return {item.item_id for item in bundle.items}


def stores():
    yield "memory", MemoryChunks()
    if store_postgres.database_is_up():
        yield "postgres", PostgresChunks(store_postgres.connect(), f"test_{uuid.uuid4().hex[:8]}")


@pytest.mark.parametrize("name, chunks", list(stores()))
def test_an_outage_at_startup_keeps_every_policy_findable_then_heals(name, chunks):
    graph = seeded(MemoryGraph(SEED["tenant_id"]), SEED)
    observe.reset_counts()

    # Step 1: the embedding service refuses; every item is stored by its words, and S5 still finds the policies
    load_chunks(chunks, graph, refusing_embed)
    assert observe.read_count("s5.seed_words_only") == 1 and len(chunks.waiting_for_vector()) == len(SEED["knowledge"])
    assert POLICIES <= search(chunks, refusing_embed)

    # Step 2: on the next start the service answers; the waiting items get their vectors and nothing is stored twice
    load_chunks(chunks, graph, fakes.fake_embed)
    assert chunks.waiting_for_vector() == [] and POLICIES <= search(chunks, fakes.fake_embed)
    assert chunks.known([k["item_id"] for k in SEED["knowledge"]]) == {k["item_id"] for k in SEED["knowledge"]}
