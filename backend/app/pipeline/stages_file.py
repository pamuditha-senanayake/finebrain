# stages_file.py: S11 File, a thin first version. A document that S2 masked becomes searchable knowledge: its text is
# split into chunks, each chunk is a knowledge node in the graph and an embedded chunk for S5, and its Library record
# moves to done. Each chunk carries the signal's domain and the entities it names (step 13a). Filing rules and version
# chains (step 14) set its type, retention and version, announced on docs.filed and docs.extracted.
# Used by: orchestrate.py (consumer of signals.normalized). Uses: contracts_signal.py, filing.py, item_tags.py, observe.py.
from datetime import datetime

from pydantic import BaseModel

from app.pipeline import filing, item_tags
from app.pipeline.contracts_signal import Signal
from app.pipeline.observe import count, log_event
from app.pipeline.retry import call_with_retry

# Config
CHUNK_CHARS = 1200
MOST_CHUNKS = 200  # a very long file keeps its first 200 chunks; the rest waits for full S11
SENSITIVITY_ORDER = ["public", "internal", "confidential", "restricted"]
EMBED_ATTEMPTS, EMBED_FIRST_WAIT = 4, 1.0  # a rate-limited embedding service (429) gets 1, 2 and 4 seconds before the message is dead-lettered


class DocumentRecord(BaseModel):
    """The Library's record of one upload. S11 moves it from pending to done or failed."""
    document_id: str
    title: str
    filename: str
    kind: str
    size_bytes: int
    uploaded_by: str
    uploaded_at: datetime
    sensitivity: str
    status: str  # pending, done, failed, retired
    original_uri: str
    chunk_ids: list[str] = []
    personal_data: bool = False
    flags: list[str] = []
    pii_tokens: list[str] = []  # vault tokens this document put there, so erasing it can clear them (step 10)
    retired_at: datetime | None = None  # set by step 10 when the document is no longer true
    domain: str = "general"  # set by S11 from the signal's domain (step 13a); older records read as general
    filing_rule: str = "uploads"  # step 14: the rule that filed it; older records read as the fallback
    doc_type: str = ""  # step 14: its Library folder type, like contract or invoice
    retention_days: int = 365
    chain_key: str = ""  # step 14: type and title stem; documents sharing it are versions of one document
    chain_id: str = ""
    version: int = 1
    superseded_by: str | None = None  # the newer version that replaced it
    evidence_for: dict | None = None  # step 16: {request_id, label, predicate, period} when uploaded to answer an evidence request


def chunks_of(text: str) -> list[str]:
    """Paragraphs packed into chunks of about CHUNK_CHARS, never splitting a paragraph unless it is longer."""
    packed, current = [], ""
    for paragraph in (p.strip(" \t\r\n") for p in text.split("\n\n")):  # not \f: a PDF page break stays, so facts know their page
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) + 2 > CHUNK_CHARS:
            packed.append(current)
            current = ""
        while len(paragraph) > CHUNK_CHARS:  # an overlong paragraph is cut, in order, after what came before it
            packed.append(paragraph[:CHUNK_CHARS])
            paragraph = paragraph[CHUNK_CHARS:]
        current = f"{current}\n\n{paragraph}" if current else paragraph
    return [chunk for chunk in [*packed, current] if chunk][:MOST_CHUNKS]


def stricter(a: str, b: str) -> str:
    return max(a, b, key=SENSITIVITY_ORDER.index)


def placement(lane, record: DocumentRecord, signal: Signal) -> dict:
    """Where the document lives: its rule, sensitivity (never lowered), domain, and place in a version chain. Announced on docs.filed."""
    rule = filing.rule_for(lane.seed, record.title, record.filename)
    key = filing.chain_key(rule["type"], record.title)
    chain_id, version, replaces = filing.chain_for(lane.records, record.document_id, key)
    placed = {"sensitivity": stricter(stricter(record.sensitivity, signal.sensitivity), rule["sensitivity"]), "domain": signal.domain or item_tags.FALLBACK,
              "filing_rule": rule["id"], "doc_type": rule["type"], "retention_days": rule["retention_days"], "chain_key": key, "chain_id": chain_id, "version": version}
    filed = {k: v for k, v in placed.items() if k != "chain_key"}
    lane.bus.publish("docs.filed", "doc.filed", filing.DocFiled(document_id=record.document_id, **filed), "ingest")
    return {**placed, "replaces": replaces}


def index_chunks(lane, record: DocumentRecord, text: str, sensitivity: str, domain: str) -> list[dict]:
    """Chunk the masked text, tag each chunk, and put it in the graph and the search index."""
    is_customer = item_tags.customer_check(lane.entities)
    items = [item_tags.tagged({
        "item_id": f"{record.document_id}_c{i}", "kind": "chunk", "text": f"{record.title}: {part}",
        "source": {"document_id": record.document_id, "uri": record.original_uri, "span": f"chunk:{i}"},
        "valid_from": record.uploaded_at.isoformat(), "valid_to": None, "recorded_at": lane.now.isoformat(), "verified_by": None,
        "version_ref": None, "score": 0.0, "sensitivity": sensitivity,
    }, domain, is_customer) for i, part in enumerate(chunks_of(text), start=1)]
    vectors = call_with_retry(lambda: lane.embed([item["text"] for item in items], "document"), lambda error: getattr(error, "retryable", False),
                              attempts=EMBED_ATTEMPTS, base_delay=EMBED_FIRST_WAIT)
    for item, vector in zip(items, vectors):
        lane.graph.put("knowledge", item["item_id"], 1, f"cmt_upload_{record.document_id}", item)
        lane.chunks.add(item, vector)
    return items


def file_document(lane, signal: Signal) -> None:
    """S11: file the document by its rule and chain, index its text, then mark it done and the version it replaces as replaced."""
    if signal.kind != "document_arrived":
        return
    document_id = signal.dedup_key.rsplit(":", 1)[-1]
    stored = lane.records.load("document", document_id)
    if stored is None or stored["status"] in ("done", "retired"):
        return  # not uploaded through the console, already filed (a redelivery), or later retired; an erased record is gone
    record = DocumentRecord.model_validate(stored)

    # Step 1: file it, then index its text
    placed = placement(lane, record, signal)
    replaces = placed.pop("replaces")
    items = index_chunks(lane, record, signal.text_masked or "", placed["sensitivity"], placed["domain"])

    # Step 2: mark it done, and the version it replaces as replaced
    lane.records.save("document", document_id, record.model_copy(update={**placed, "status": "done", "chunk_ids": [item["item_id"] for item in items],
                      "personal_data": bool(signal.pii_tokens), "flags": signal.flags, "pii_tokens": list(signal.pii_tokens)}))
    if replaces:
        older = DocumentRecord.model_validate(lane.records.load("document", replaces))
        lane.records.save("document", replaces, older.model_copy(update={"superseded_by": document_id}))
    lane.bus.publish("docs.extracted", "doc.extracted", filing.DocExtracted(document_id=document_id, chunk_count=len(items), characters=len(signal.text_masked or "")), "ingest")
    count("s11.filed")
    log_event("S11", "filed", document_id=document_id, chunks=len(items), domain=placed["domain"], rule=placed["filing_rule"], version=placed["version"])
