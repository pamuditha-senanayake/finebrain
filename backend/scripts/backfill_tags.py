# backfill_tags.py: step 13a. Tags what was stored before tagging existed: the entities of old signals, the domain and
# entity tags of old chunks, and the domain of old Library records. Safe to run twice: tagged chunks are skipped and
# entity notes are idempotent. Run from backend/ with Docker up:  uv run --env-file .env python -m scripts.backfill_tags
# Without ANTHROPIC_API_KEY, old uploads are filed under general. Tests import backfill.
# Uses: hq.py (seed), self_knowledge.py, store_postgres.py, store_chunks_pg.py, store_entities.py, entity_match.py, item_tags.py, llm.py.
import os
from datetime import datetime, timezone

from app.api import self_knowledge
from app.api.hq import load_hq
from app.pipeline import entity_match, item_tags, llm, store_postgres
from app.pipeline.contracts_signal import Signal
from app.pipeline.stages_file import DocumentRecord
from app.pipeline.store_chunks_pg import PostgresChunks
from app.pipeline.store_entities import PostgresEntities


# --- Helpers

def tag_signals(records, entities, now: datetime) -> int:
    """Note the entities of every stored signal. Returns how many signals were read."""
    signals = records.list_kind("signal")
    for body in signals:
        entity_match.record_entities(entities, Signal.model_validate(body), now)
    return len(signals)


def domain_for(item: dict, records, seed: dict, classifier, known: dict) -> str:
    """An upload is classified once, from its first chunk; the brain's own knowledge is general; the rest is the pipeline's domain."""
    document_id = item.get("source", {}).get("document_id", "")
    if document_id == self_knowledge.DOCUMENT_ID:
        return "general"
    if records.load("document", document_id) is None:
        return item_tags.default_domain(seed)
    if document_id not in known:
        known[document_id] = item_tags.classify(classifier, item["text"])
    return known[document_id]


def tag_documents(records, known: dict) -> int:
    """Save the domain on each Library record that has none yet, as a new version."""
    untagged = [record for record in records.list_kind("document") if "domain" not in record and record["document_id"] in known]
    for record in untagged:
        records.save("document", record["document_id"], DocumentRecord.model_validate(record).model_copy(update={"domain": known[record["document_id"]]}))
    return len(untagged)


# --- The back-fill

def backfill(records, chunks, entities, seed: dict, classifier, now: datetime) -> dict:
    """Signals first, so customers they name are known when chunk tokens are checked."""
    # Step 1: the registry learns what old signals were about
    signals = tag_signals(records, entities, now)

    # Step 2: each untagged chunk gets its domain and the entities its text names
    known, is_customer, untagged = {}, item_tags.customer_check(entities), chunks.untagged()
    for item in untagged:
        chunks.retag(item["item_id"], domain_for(item, records, seed, classifier, known), item_tags.entities_in_text(item["text"], is_customer))

    # Step 3: Library records carry their document's domain
    documents = tag_documents(records, known)
    return {"signals": signals, "chunks": len(untagged), "documents": documents, "entities": len(entities.all())}


def main() -> None:
    seed, _ = load_hq()
    connection = store_postgres.connect()
    tenant = seed["tenant_id"]
    classifier = llm.make_chooser(system=llm.DOMAIN_SYSTEM) if os.environ.get("ANTHROPIC_API_KEY") else None
    done = backfill(store_postgres.PostgresRecords(connection, tenant), PostgresChunks(connection, tenant), PostgresEntities(connection, tenant),
                    seed, classifier, datetime.now(timezone.utc))
    print(f"{tenant}: {done['signals']} signals read, {done['chunks']} chunks tagged, {done['documents']} Library records tagged, "
          f"{done['entities']} entities in the registry")


if __name__ == "__main__":
    main()
