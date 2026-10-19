# test_forget_stores.py: the new forgetting calls on every store, memory and Postgres alike: records purge, graph purge,
# chunks of_document, retire and delete. Postgres checks skip when nothing answers on localhost:5433, and the chunk
# checks also skip when that Postgres has no pgvector. Uses: store_memory.py, store_postgres.py, store_graph.py, store_chunks.py.
import uuid
from datetime import timedelta

import psycopg
import pytest

from app.pipeline.contracts_run import RunRecord
from app.pipeline.store_chunks import MemoryChunks
from app.pipeline.store_chunks_pg import PostgresChunks
from app.pipeline.store_graph import MemoryGraph, PostgresGraph
from app.pipeline.store_memory import MemoryRecords
from app.pipeline.store_postgres import PostgresRecords, connect, database_is_up
from tests.golden import NOW, golden

# Config
APPROVAL = RunRecord.model_validate(golden("s3", "RunRecord"))
NEEDS_POSTGRES = pytest.mark.skipif(not database_is_up(), reason="no Postgres on localhost:5433")


def tenant() -> str:
    return f"test_{uuid.uuid4().hex[:8]}"


def chunk(item_id: str, text: str) -> dict:
    return {"item_id": item_id, "kind": "chunk", "text": text, "source": {"document_id": "doc_1"}, "valid_from": NOW.isoformat(), "valid_to": None, "recorded_at": NOW.isoformat()}


def vector(first: float) -> list[float]:
    return [first] + [0.0] * 1023


@pytest.fixture(params=["memory", pytest.param("postgres", marks=NEEDS_POSTGRES)])
def records(request):
    return MemoryRecords("t") if request.param == "memory" else PostgresRecords(connect(), tenant())


@pytest.fixture(params=["memory", pytest.param("postgres", marks=NEEDS_POSTGRES)])
def graph(request):
    return MemoryGraph("t") if request.param == "memory" else PostgresGraph(connect(), tenant())


def test_records_purge_removes_every_version_and_returns_them(records):
    records.save("approval", "a1", APPROVAL)
    records.save("approval", "a1", APPROVAL)
    records.save("approval", "a2", APPROVAL)
    assert len(records.purge("approval", "a1")) == 2
    assert records.load("approval", "a1") is None and records.history("approval", "a1") == []
    assert records.load("approval", "a2") and records.purge("approval", "a1") == []


def test_graph_purge_empties_every_version_but_keeps_the_history(graph):
    graph.put("knowledge", "k1", 1, "c1", {"text": "secret"})
    graph.put("knowledge", "k1", 2, "c2", {"text": "secret again"})
    graph.put("knowledge", "k2", 1, "c1", {"text": "other"})
    graph.purge("knowledge", "k1")
    assert [node["_ref"]["id"] for node in graph.latest("knowledge")] == ["k2"]
    history = graph.history("knowledge", "k1")
    assert [node["_ref"]["version"] for node in history] == [1, 2] and all("text" not in node and node["_erased"] for node in history)


def vector_chunks():
    """Postgres chunks, or a skip when this Postgres has no pgvector."""
    if not database_is_up():
        pytest.skip("no Postgres on localhost:5433")
    try:
        return PostgresChunks(connect(), tenant())
    except psycopg.errors.Error:
        pytest.skip("no pgvector in this Postgres")


@pytest.fixture(params=["memory", "postgres"])
def chunks(request):
    return MemoryChunks() if request.param == "memory" else vector_chunks()


def test_chunks_of_document_retire_and_delete(chunks):
    chunks.add(chunk("doc_1_c1", "refund window thirty days"), vector(1.0))
    chunks.add(chunk("doc_1_c2", "refund exceptions annual plans"), vector(0.9))
    chunks.add({**chunk("other_c1", "refund other"), "source": {"document_id": "other"}}, vector(0.8))
    assert [c["item_id"] for c in chunks.of_document("doc_1")] == ["doc_1_c1", "doc_1_c2"]
    later = NOW + timedelta(days=2)
    chunks.retire("doc_1_c1", NOW + timedelta(days=1))
    today = {c["item_id"] for c in chunks.by_text("refund", ["chunk"], later, later, 10)}
    before = {c["item_id"] for c in chunks.by_text("refund", ["chunk"], NOW + timedelta(hours=1), later, 10)}
    assert today == {"doc_1_c2", "other_c1"} and before == {"doc_1_c1", "doc_1_c2", "other_c1"}
    chunks.delete("doc_1_c2")
    assert [c["item_id"] for c in chunks.of_document("doc_1")] == ["doc_1_c1"]
