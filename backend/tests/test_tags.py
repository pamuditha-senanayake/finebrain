# test_tags.py: step 13a, the four tags. Signals get a domain and entity ids at S2, every chunk gets a domain and the
# entities its text names (seed, uploads, releases), and the back-fill tags what was stored before. Memory, and Postgres when up.
# Uses: app/pipeline/item_tags.py, stages_file.py, stages_version.py, store_chunks*.py, scripts/backfill_tags.py, tests/test_documents.py.
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.routes import create_api_app
from app.pipeline import fakes, item_tags, orchestrate, stages_version, store_postgres
from app.pipeline.contracts_graph import CommitAuthor
from app.pipeline.entity_match import entity_id_of
from app.pipeline.stages_version import Draft
from app.pipeline.store_chunks import MemoryChunks, load_chunks
from app.pipeline.store_chunks_pg import PostgresChunks
from app.pipeline.store_entities import MemoryEntities
from app.pipeline.store_memory import MemoryRecords
from scripts.backfill_tags import backfill
from tests.golden import NOW, raw_sample
from tests.test_documents import HQ, SEED, upload

# Config
PAYMENT = "pay_FB_20261004_0192"
INVOICE = b"Supplier invoice\n\nInvoice 2041 from Lanka Print for LKR 40,000, paid by bank transfer."
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")


# --- Helpers

def finance_or_nothing(text: str, options: dict) -> str | None:
    """A stand-in for Claude: invoices are finance, anything else gets no answer."""
    return "finance" if "invoice" in text.lower() else None


def build(classify=finance_or_nothing):
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, classify=classify)
    return TestClient(create_api_app(lane, HQ)), lane


def filed_chunks(client, lane, name: str, data: bytes) -> list[dict]:
    document_id = upload(client, name, data).json()["id"]
    lane.bus.drain()
    return lane.chunks.of_document(document_id)


# --- At intake

def test_a_message_takes_its_clusters_domain_and_names_its_entities():
    client, lane = build()
    orchestrate.capture_signal(lane, raw_sample("s2"))
    lane.bus.drain()
    signal = lane.bus.topics["signals.normalized"][0].payload
    assert signal["domain"] == "customer_care" and entity_id_of("payment", PAYMENT) in signal["entity_ids"]


def test_an_upload_is_classified_and_its_chunks_carry_the_tags():
    client, lane = build()
    chunks = filed_chunks(client, lane, "invoice_2041.md", INVOICE)
    assert chunks and {chunk["domain"] for chunk in chunks} == {"finance"} and all(chunk["entity_ids"] == [] for chunk in chunks)
    assert {record["domain"] for record in lane.records.list_kind("document")} == {"finance"}


def test_a_chunk_naming_a_payment_is_tagged_with_it():
    client, lane = build()
    chunks = filed_chunks(client, lane, "refund_note.md", f"Refund note\n\nPayment {PAYMENT} was refunded.".encode())
    assert chunks[0]["entity_ids"] == [entity_id_of("payment", PAYMENT)]


@pytest.mark.parametrize("classify", [None, finance_or_nothing, lambda text, options: 1 / 0])
def test_no_answer_or_an_outage_files_an_upload_under_general(classify):
    client, lane = build(classify)
    chunks = filed_chunks(client, lane, "support_hours.md", b"Support hours\n\nWe answer from 8 am to 6 pm.")
    assert {chunk["domain"] for chunk in chunks} == {"general"}


def test_seed_knowledge_is_tagged_on_load():
    _, lane = build()
    items = {item["item_id"]: item for item, _ in lane.chunks.items.values()}
    assert all(item["domain"] in item_tags.DOMAINS for item in items.values())
    assert items["item_payment_s2"]["entity_ids"] == [entity_id_of("payment", PAYMENT)]
    assert items["item_policy_window"]["entity_ids"] == [] and items["self_who_i_am"]["domain"] == "general"


def test_a_released_item_is_tagged_again():
    _, lane = build()
    node = next(node for node in lane.graph.latest("knowledge") if node["_ref"]["id"] == "item_policy_window")
    fields = {key: value for key, value in node.items() if key != "_ref"} | {"text": f"Refunds within 30 days, for example {PAYMENT}."}
    draft = Draft(op="update", node_type="knowledge", node_id="item_policy_window", fields=fields, base_version=node["_ref"]["version"])
    stages_version.apply(lane, CommitAuthor(kind="human", id="h-pamuditha"), "Edit the window", [draft], 1)
    lane.bus.drain()
    item = lane.chunks.items["item_policy_window"][0]
    assert item["domain"] == "customer_care" and item["entity_ids"] == [entity_id_of("payment", PAYMENT)]


# --- The back-fill

class OldDocument(BaseModel):
    """A Library record as saved before step 13a: no domain."""
    document_id: str
    title: str = "Invoice 9"
    filename: str = "invoice_9.md"
    kind: str = ".md"
    size_bytes: int = 30
    uploaded_by: str = "h-pamuditha"
    uploaded_at: str = NOW.isoformat()
    sensitivity: str = "internal"
    status: str = "done"
    original_uri: str = "s3://brain/doc_9"


def untagged(item_id: str, text: str, document_id: str) -> dict:
    return {"item_id": item_id, "kind": "chunk", "text": text, "source": {"document_id": document_id}, "recorded_at": NOW.isoformat()}


def test_the_backfill_tags_old_chunks_once():
    records, chunks, entities = MemoryRecords(SEED["tenant_id"]), MemoryChunks(), MemoryEntities()
    chunks.add(untagged("seed_c1", f"Payment {PAYMENT} was made.", "doc_billing"), [1.0])
    chunks.add(untagged("doc_9_c1", "Invoice 9 from Lanka Print.", "doc_9"), [1.0])
    records.save("document", "doc_9", OldDocument(document_id="doc_9"))
    done = backfill(records, chunks, entities, SEED, finance_or_nothing, NOW)
    assert done["chunks"] == 2 and done["documents"] == 1 and chunks.untagged() == []
    assert chunks.items["seed_c1"][0]["entity_ids"] == [entity_id_of("payment", PAYMENT)] and chunks.items["doc_9_c1"][0]["domain"] == "finance"
    assert backfill(records, chunks, entities, SEED, finance_or_nothing, NOW)["chunks"] == 0


@NEEDS_POSTGRES
def test_postgres_chunks_keep_tags_in_columns():
    chunks = PostgresChunks(store_postgres.connect(), f"test_tags_{uuid.uuid4().hex[:8]}")
    chunks.add(untagged("c1", "old words", "doc_old"), [0.5] * 1024)
    assert [item["item_id"] for item in chunks.untagged()] == ["c1"]
    chunks.retag("c1", "finance", ["ent_payment_x"])
    row = chunks.connection.execute("SELECT domain, entity_ids, body->>'domain' FROM chunks WHERE tenant_id = %s", (chunks.tenant_id,)).fetchone()
    assert row == ("finance", ["ent_payment_x"], "finance") and chunks.untagged() == []
    chunks.delete("c1")


def test_a_restart_embeds_nothing_already_indexed_and_survives_a_refusing_embedder():
    _, lane = build()
    calls = []
    load_chunks(lane.chunks, lane.graph, lambda texts, kind: calls.append(texts) or [[1.0]] * len(texts))
    assert calls == []  # every seed item is already in the index
    lane.chunks.delete("item_policy_window")
    def refusing(texts, kind):
        raise RuntimeError("voyage /embeddings answered 429")
    load_chunks(lane.chunks, lane.graph, refusing)
    assert "item_policy_window" not in lane.chunks.items  # not loaded, and no crash: it waits for the next start
