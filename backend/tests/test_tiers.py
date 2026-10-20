# test_tiers.py: step 13c slice 2, tiers and budgets. The best open items fill hot up to its budget, the rest stay warm
# while their entity (or domain) has room, overflow and long-closed facts go cold. Search reads hot first; only a
# question about the past reads cold; forgetting reaches every tier. Runs on memory, and on Postgres when it answers.
# Uses: app/pipeline/stages_tiers.py, store_chunks.py, store_chunks_tiers.py, tests/test_scope.py, test_forget.py.
import uuid
from datetime import timedelta

import pytest

from app.pipeline import stages_tiers, store_postgres
from app.pipeline.store_chunks import MemoryChunks
from app.pipeline.store_chunks_pg import PostgresChunks
from tests.golden import NOW
from tests.test_documents import build
from tests.test_forget import filed, remove
from tests.test_scope import filled

# Config
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")
SMALL = {"hot": 2, "warm_per_entity": 1, "warm_per_domain": 1, "closed_grace_days": 30}
KINDS = ["policy", "fact", "chunk"]
PAST = NOW - timedelta(days=30)


def row(item_id: str, value: float, entity: str | None = None, domain: str = "finance", valid_to=None) -> dict:
    return {"item_id": item_id, "value": value, "entity_ids": [entity] if entity else [], "domain": domain, "valid_to": valid_to and valid_to.isoformat()}


def hits(chunks, words: str, valid=NOW) -> list[str]:
    return [item["item_id"] for item in chunks.by_text(words, KINDS, valid, NOW, 50)]


# --- Placing

def test_the_best_fill_hot_then_each_entity_keeps_its_budget_and_the_rest_go_cold():
    rows = [row("a", 9), row("b", 8), row("c", 7, "e1"), row("d", 6, "e1"), row("e", 5), row("f", 4),
            row("old", 99, valid_to=NOW - timedelta(days=31)), row("recent", 98, "e2", valid_to=NOW - timedelta(days=1))]
    assert stages_tiers.place(rows, NOW, SMALL) == {"old": "cold", "recent": "warm", "a": "hot", "b": "hot", "c": "warm", "d": "cold", "e": "warm", "f": "cold"}


def test_a_pass_stores_only_what_changed_and_says_what_it_did():
    _, lane = build()
    first = stages_tiers.move(lane, SMALL)
    assert (first.hot, first.hot + first.warm + first.cold) == (2, len(lane.chunks.value_rows()))
    assert stages_tiers.move(lane, SMALL).moved == 0 and lane.records.load(stages_tiers.RUN_KIND, "latest")["moved"] == 0


# --- Reading by tier

def check_reading(chunks) -> None:
    """Hot comes first; cold is left out of today's questions and found by questions about the past."""
    chunks.set_tiers({"item_policy_auto_limit": "hot", "item_policy_window": "cold"})
    assert hits(chunks, "refund")[0] == "item_policy_auto_limit"
    assert "item_policy_window" not in hits(chunks, "refund window")
    assert "item_policy_window" in hits(chunks, "refund window", valid=PAST)


def test_memory_reads_hot_first_and_cold_only_for_history():
    check_reading(filled(MemoryChunks()))


@NEEDS_POSTGRES
def test_postgres_reads_the_same_way():
    chunks = filled(PostgresChunks(store_postgres.connect(), f"test_tiers_{uuid.uuid4().hex[:8]}"))
    check_reading(chunks)
    assert {row["item_id"]: row["tier"] for row in chunks.value_rows()}["item_policy_window"] == "cold"


# --- Forgetting

def test_erasing_a_document_reaches_its_cold_chunks():
    client, lane = build()
    document_id = filed(client, lane)
    lane.chunks.set_tiers({item["item_id"]: "cold" for item in lane.chunks.of_document(document_id)})
    assert remove(client, document_id, "erase")["status"] == "done" and lane.chunks.of_document(document_id) == []
