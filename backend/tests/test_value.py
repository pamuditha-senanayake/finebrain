# test_value.py: step 13c slice 1, use and value. Runs and Ask answers record what they cite, once each; every item gets
# value = use x recency x risk x trust x links (a closed one keeps a tenth), stored on the chunk. Runs on memory, and on
# Postgres when it answers. Uses: app/pipeline/stages_value.py, store_uses.py, store_chunks_tiers.py, api/memory_routes.py, tests/test_api.py.
import uuid
from datetime import timedelta

import pytest

from app.pipeline import stages_value, store_postgres
from app.pipeline.store_chunks_pg import PostgresChunks
from app.pipeline.store_uses import MemoryUses, PostgresUses
from tests.golden import NOW
from tests.test_api import FOUNDER, TENANT, hq  # noqa: F401  (hq: s2 resolved and s3 waiting, both citing the refund policy)

# Config
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")
WINDOW = "item_policy_window"  # both golden runs cite it
ITEM = {"item_id": "c1", "kind": "chunk", "domain": "customer_care", "entity_ids": [], "valid_to": None, "recorded_at": NOW.isoformat()}


# --- The score

def test_an_ordinary_item_scores_one_and_each_factor_multiplies():
    def value(uses=0, last=None, **changes):
        return stages_value.value_of({**ITEM, **changes}, uses, last, NOW)
    assert value() == 1.0
    assert value(uses=3, last=NOW) == 3.0  # 1 + log2(1 + 3)
    assert value(recorded_at=(NOW - timedelta(days=60)).isoformat()) == 0.25  # two half lives
    assert (value(kind="fact"), value(kind="policy"), value(domain="finance")) == (1.5, 3.0, 2.0)
    assert value(entity_ids=["e1", "e2"]) == 1.5
    assert value(valid_to=(NOW - timedelta(days=1)).isoformat()) == 0.1


# --- Uses

def test_runs_and_answers_count_their_citations_once(hq):
    client, lane, _ = hq
    assert lane.uses.uses_of([WINDOW])[WINDOW][0] == 2  # s2 and s3
    assert sum(stages_value.note_run(lane, run) for run in lane.records.list_kind("run")) == 0  # a redelivery adds nothing
    answer = client.post(f"/api/t/{TENANT}/ask", json={"question": "What is the refund window?"}, headers={"x-persona": FOUNDER}).json()
    cited = [c["id"] for c in answer["citations"]]
    assert cited and all(lane.uses.uses_of(cited)[item_id][0] >= 1 for item_id in cited)


# --- Scores on the items

def test_every_item_has_a_value_and_a_cited_one_scores_higher(hq):
    _, lane, _ = hq
    rows = {row["item_id"]: row for row in lane.chunks.value_rows()}
    assert rows and all(row["value"] is not None for row in rows.values())
    stages_value.score_all(lane)
    rows = {row["item_id"]: row for row in lane.chunks.value_rows()}
    uncited = [row for row in rows.values() if row["kind"] == rows[WINDOW]["kind"] and not lane.uses.uses_of([row["item_id"]])]
    assert uncited and rows[WINDOW]["value"] > max(row["value"] for row in uncited)


# --- Postgres

@NEEDS_POSTGRES
def test_postgres_gives_the_same_answers_as_memory():
    connection, tenant = store_postgres.connect(), f"test_value_{uuid.uuid4().hex[:8]}"
    uses = [MemoryUses(), PostgresUses(connection, tenant)]
    for store in uses:
        assert store.note("a", "run_1", NOW) and store.note("a", "run_2", NOW + timedelta(hours=1)) and not store.note("a", "run_1", NOW)
    assert uses[0].uses_of(["a", "b"]) == uses[1].uses_of(["a", "b"]) == {"a": (2, NOW + timedelta(hours=1))}
    chunks = PostgresChunks(connection, tenant)
    chunks.add({**ITEM, "text": "Refunds within 30 days."}, [0.1] * 1024)
    chunks.set_values({"c1": 2.5, "unknown": 9.0}, NOW)
    assert [(row["item_id"], row["value"]) for row in chunks.value_rows()] == [("c1", 2.5)]
