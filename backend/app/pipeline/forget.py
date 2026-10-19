# forget.py: step 10, forgetting. Every layer that holds knowledge registers a handler (retire, erase, verify); the job
# runs them all, checks that nothing is left, and returns a receipt. Used by: api/forget_review.py, tests/test_forget.py.
# Uses: observe.py. The layers themselves live in api/forget_layers.py and api/forget_layers_data.py.
# Retire: no longer true, so today's search stops finding it and an "as of" search still does.
# Erase: gone from every layer. Only a tombstone stays: who, when and why, never the content.
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel

from app.pipeline.lane import Lane
from app.pipeline.observe import count, log_event

# Config
MODES = ("retire", "erase")
PROBE_WORDS = 12  # distinctive words kept in memory during one job, to search again afterwards
NOT_CONTENT = {"seed", "model", "gateway", "now", "new_id", "embed", "rerank", "check_access", "tooling", "audit", "broadcaster",
               "grade", "choose", "runner", "approvals", "pending"}  # a new Lane field must be listed here or covered by a layer


@dataclass
class ForgetItem:
    """What one document put into the layers. Built before anything is removed."""
    document_id: str
    record: dict
    chunk_ids: list[str] = field(default_factory=list)
    probes: list[str] = field(default_factory=list)


class Layer(Protocol):
    name: str  # shown on the receipt
    stores: tuple[str, ...]  # the Lane fields this layer clears
    final: bool  # runs only once every other layer verified clean, so a half-done job can still find the document

    def retire(self, lane: Lane, item: ForgetItem) -> tuple[str, str]: ...  # (result, note)
    def erase(self, lane: Lane, item: ForgetItem) -> tuple[str, str]: ...  # result: cleared, kept or nothing
    def verify(self, lane: Lane, item: ForgetItem, mode: str) -> bool: ...


class Tombstone(BaseModel):
    """All that is left of an erased document."""
    document_id: str
    erased_by: str
    erased_at: datetime
    reason: str
    layers: list[str]


LAYERS: list[Layer] = []


def register(layer: Layer) -> Layer:
    LAYERS.append(layer)
    return layer


def uncovered_stores() -> list[str]:
    """Lane fields that hold data but have no layer. Empty when every store knows how to forget."""
    covered = {store for layer in LAYERS for store in layer.stores}
    return sorted(f.name for f in fields(Lane) if f.name not in NOT_CONTENT and f.name not in covered)


def probe_words(texts: list[str]) -> list[str]:
    """The longest words of the chunks, which a search would find them by."""
    words = {word for text in texts for word in text.lower().split() if word.isalpha() and len(word) >= 6}
    return sorted(words, key=lambda word: (-len(word), word))[:PROBE_WORDS]


def item_of(lane: Lane, document_id: str) -> ForgetItem:
    """Gather what the document holds. KeyError when it is not in the Library."""
    record = lane.records.load("document", document_id)
    if record is None:
        raise KeyError(document_id)
    bodies = lane.chunks.of_document(document_id)
    chunk_ids = sorted({*record.get("chunk_ids", []), *(body["item_id"] for body in bodies)})
    return ForgetItem(document_id, record, chunk_ids, probe_words([body["text"] for body in bodies]))


def run(lane: Lane, document_id: str, mode: str, by: str, reason: str) -> dict:
    """Run every layer, then search again. The receipt says what each layer did and whether the check came back clean.
    Safe to run twice: a layer that has nothing left reports "nothing"."""
    if mode not in MODES:
        raise ValueError(mode)
    item = item_of(lane, document_id)
    steps, failed = [], []
    for final in (False, True):
        if failed:
            break
        phase = [layer for layer in LAYERS if layer.final is final]
        for layer in phase:
            result, note = (layer.retire if mode == "retire" else layer.erase)(lane, item)
            steps.append({"layer": layer.name, "result": result, "note": note})
        failed = [layer.name for layer in phase if not layer.verify(lane, item, mode)]
    receipt = {"mode": mode, "at": lane.now.isoformat(), "by": by, "layers": steps, "verified": not failed, "failed": failed}
    if not failed:
        if mode == "erase":
            lane.records.save("tombstone", document_id, Tombstone(document_id=document_id, erased_by=by, erased_at=lane.now, reason=reason, layers=[s["layer"] for s in steps]))
        lane.audit.append(f"forget:{document_id}:{mode}", "forget.completed", {"document_id": document_id, "mode": mode, "by": by, "at": lane.now.isoformat(), "reason": reason})
    count(f"forget.{mode}")
    log_event("FORGET", mode, document_id=document_id, verified=not failed)
    return receipt
