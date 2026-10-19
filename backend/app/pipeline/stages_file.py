# stages_file.py: S11 File, a thin first version. A document that S2 masked becomes searchable knowledge: its text is
# split into chunks, each chunk is a knowledge node in the graph and an embedded chunk for S5, and its Library record
# moves to done. Used by: orchestrate.py (consumer of signals.normalized). Uses: contracts_signal.py, observe.py.
from datetime import datetime

from pydantic import BaseModel

from app.pipeline.contracts_signal import Signal
from app.pipeline.observe import count, log_event

# Config
CHUNK_CHARS = 1200
MOST_CHUNKS = 200  # a very long file keeps its first 200 chunks; the rest waits for full S11
SENSITIVITY_ORDER = ["public", "internal", "confidential", "restricted"]


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


def chunks_of(text: str) -> list[str]:
    """Paragraphs packed into chunks of about CHUNK_CHARS, never splitting a paragraph unless it is longer."""
    packed, current = [], ""
    for paragraph in (p.strip() for p in text.split("\n\n")):
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


def file_document(lane, signal: Signal) -> None:
    """S11: chunk the masked text into the graph and the search index, then mark the Library record done."""
    if signal.kind != "document_arrived":
        return
    document_id = signal.dedup_key.rsplit(":", 1)[-1]
    stored = lane.records.load("document", document_id)
    if stored is None or stored["status"] in ("done", "retired"):
        return  # not uploaded through the console, already filed (a redelivery), or later retired; an erased record is gone
    record = DocumentRecord.model_validate(stored)
    sensitivity = stricter(record.sensitivity, signal.sensitivity)
    items = [{
        "item_id": f"{document_id}_c{i}", "kind": "chunk", "text": f"{record.title}: {text}",
        "source": {"document_id": document_id, "uri": record.original_uri, "span": f"chunk:{i}"},
        "valid_from": record.uploaded_at.isoformat(), "valid_to": None, "recorded_at": lane.now.isoformat(), "verified_by": None,
        "version_ref": None, "score": 0.0, "sensitivity": sensitivity,
    } for i, text in enumerate(chunks_of(signal.text_masked or ""), start=1)]
    for item, vector in zip(items, lane.embed([item["text"] for item in items], "document")):
        lane.graph.put("knowledge", item["item_id"], 1, f"cmt_upload_{document_id}", item)
        lane.chunks.add(item, vector)
    lane.records.save("document", document_id, record.model_copy(update={
        "status": "done", "sensitivity": sensitivity, "chunk_ids": [item["item_id"] for item in items],
        "personal_data": bool(signal.pii_tokens), "flags": signal.flags, "pii_tokens": list(signal.pii_tokens),
    }))
    count("s11.filed")
    log_event("S11", "filed", document_id=document_id, chunks=len(items), sensitivity=sensitivity)
