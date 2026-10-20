# test_cold.py: step 13c slice 3, the cold and raw tiers. An item going cold is archived to S3 with its vector and Postgres
# keeps only its words; history still finds it by words; coming back up restores the vector. Erasing a document removes
# its cold copies. Raw bodies past 90 days are deleted with a tombstone and an audit entry, after a dry run.
# Uses: app/pipeline/stages_cold.py, stages_tiers.py, api/forget_layers.py (ColdLayer), tests/test_tiers.py, test_forget.py.
import gzip
import json
import uuid
from datetime import timedelta

import pytest

from app.pipeline import fakes, orchestrate, stages_cold, stages_tiers, store_postgres
from app.pipeline.store_chunks_pg import PostgresChunks
from tests.golden import NOW, SEED
from tests.test_documents import build
from tests.test_forget import filed, library, remove
from tests.test_tiers import KINDS, PAST, SMALL, hits

# Config
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")
WINDOW = "item_policy_window"
NONE_HOT = {**SMALL, "hot": 0, "warm_per_entity": 0, "warm_per_domain": 0}  # everything goes cold
ROOMY = {**SMALL, "hot": 1000, "warm_per_entity": 1000, "warm_per_domain": 1000}


def lane_of():
    return orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)


def vector_hits(lane, valid=NOW) -> list[str]:
    return [item["item_id"] for item in lane.chunks.by_vector(fakes.fake_embed(["refund window"])[0], KINDS, valid, NOW, 50)]


# --- Cold

def test_going_cold_archives_the_vector_and_keeps_the_words_for_history():
    lane = lane_of()
    stages_tiers.move(lane, NONE_HOT)
    archived = json.loads(gzip.decompress(lane.object_store[stages_cold.cold_uri(lane, WINDOW)]))
    assert archived["item"]["item_id"] == WINDOW and len(archived["embedding"]) > 0
    assert lane.chunks.full(WINDOW)[1] is None  # the vector left
    assert WINDOW in hits(lane.chunks, "refund window", valid=PAST) and WINDOW not in vector_hits(lane, valid=PAST)
    assert WINDOW not in hits(lane.chunks, "refund window")  # today's questions do not read cold


def test_an_item_already_cold_without_an_archive_is_archived():
    lane = lane_of()
    lane.chunks.set_tiers({WINDOW: "cold"})  # cold from before the archive existed, vector still in place
    stages_tiers.move(lane, {**ROOMY, "hot": 0, "warm_per_domain": 0, "warm_per_entity": 0})
    assert lane.chunks.full(WINDOW)[1] is None and stages_cold.cold_uri(lane, WINDOW) in lane.object_store


def test_coming_back_up_restores_the_vector_and_drops_the_archive():
    lane = lane_of()
    before = lane.chunks.full(WINDOW)[1]
    stages_tiers.move(lane, NONE_HOT)
    stages_tiers.move(lane, ROOMY)
    assert lane.chunks.full(WINDOW)[1] == before and stages_cold.cold_uri(lane, WINDOW) not in lane.object_store
    assert WINDOW in vector_hits(lane)


def test_erasing_a_document_removes_its_cold_copies():
    client, lane = build()
    document_id = filed(client, lane)
    chunk_ids = [item["item_id"] for item in lane.chunks.of_document(document_id)]
    stages_cold.freeze(lane, chunk_ids)
    assert all(stages_cold.cold_uri(lane, chunk_id) in lane.object_store for chunk_id in chunk_ids)
    remove(client, document_id, "erase")
    assert not any(stages_cold.cold_uri(lane, chunk_id) in lane.object_store for chunk_id in chunk_ids)
    assert library(client)[0]["receipt"]["verified"]


# --- Raw retention

def test_raw_bodies_past_ninety_days_go_after_a_dry_run():
    lane = lane_of()
    old, new = (f"s3://brain/{SEED['tenant_id']}/raw/{day:%Y/%m/%d}/mail.eml" for day in (NOW - timedelta(days=91), NOW - timedelta(days=89)))
    lane.object_store.update({old: b"old", new: b"new"})
    assert stages_cold.sweep_raw(lane, apply=False) == {"due": 1, "deleted": 0} and old in lane.object_store
    assert stages_cold.sweep_raw(lane, apply=True) == {"due": 1, "deleted": 1}
    assert old not in lane.object_store and new in lane.object_store
    assert lane.records.load(stages_cold.TOMBSTONE_KIND, old)["reason"] == "raw retention of 90 days ended"
    assert [e["topic"] for e in lane.audit.in_order() if e["topic"].startswith("retention.")] == ["retention.raw_deleted"]


# --- Postgres

@NEEDS_POSTGRES
def test_postgres_drops_and_restores_a_vector():
    chunks = PostgresChunks(store_postgres.connect(), f"test_cold_{uuid.uuid4().hex[:8]}")
    item = {"item_id": "c1", "kind": "chunk", "text": "Refunds within 30 days.", "recorded_at": NOW.isoformat(), "valid_from": None, "valid_to": None}
    vector = fakes.fake_embed([item["text"]])[0]
    chunks.add(item, vector)
    chunks.set_vector("c1", None)
    assert chunks.full("c1")[1] is None and chunks.by_vector(vector, ["chunk"], NOW, NOW, 5) == []
    chunks.set_vector("c1", vector)
    assert chunks.full("c1")[1] == pytest.approx(vector, abs=1e-6) and [i["item_id"] for i in chunks.by_vector(vector, ["chunk"], NOW, NOW, 5)] == ["c1"]
