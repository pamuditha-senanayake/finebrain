# stages_librarian.py: step 14 slice 3, S12 Librarian (B08). Each K12 candidate is compared with the facts already true about
# the same thing and the same predicate, and becomes one review item: unverified (new, waiting for a person), duplicate (same
# value, closed at once), stale (its validity already ended) or conflict (a different value; slice 4 drafts the resolution).
# Used by: orchestrate.py (consumer of facts.candidates), fact_commit.py, api/vault_views.py, tests. Uses: stages_extract.py, observe.py.
from datetime import datetime

from pydantic import BaseModel

from app.pipeline import stages_extract
from app.pipeline.contracts_signal import Envelope, FactCandidate
from app.pipeline.observe import count, log_event

# Config
ITEM_KIND = "librarian_item"
FACT_NODE = "fact"  # verified facts are graph nodes of this type, written through S14


class LibrarianItem(BaseModel):
    """One candidate in the review queue, and how it was settled."""
    item_id: str
    kind: str  # unverified, duplicate, stale, conflict
    title: str
    detail: str
    candidate_id: str
    document_id: str
    fact_ids: list[str]  # the facts it duplicates or conflicts with, then the fact it became
    status: str  # open, resolved
    resolution: str | None = None  # accepted, rejected, duplicate
    decided_by: str | None = None
    decided_at: datetime | None = None
    change_request_id: str | None = None  # slice 4: a conflict's change request
    created_at: datetime


def item_id_of(candidate_id: str) -> str:
    return "li_" + candidate_id.removeprefix("fc_")


def plain(value: str) -> str:
    return " ".join(str(value).lower().split())


# --- Comparing with ground truth

def true_facts(lane, candidate: FactCandidate) -> list[dict]:
    """Facts on main about the same thing and predicate that are still true now."""
    return [fact for fact in lane.graph.latest(FACT_NODE) if fact["subject"]["entity_ref"] == candidate.subject.entity_ref
            and fact["predicate"] == candidate.predicate and (not fact.get("valid_to") or datetime.fromisoformat(fact["valid_to"]) > lane.now)]


def classify(lane, candidate: FactCandidate) -> tuple[str, list[str]]:
    """The kind of review item, and the facts it relates to."""
    if candidate.valid_to and candidate.valid_to < lane.now:
        return "stale", []
    current = true_facts(lane, candidate)
    same = [fact["item_id"] for fact in current if plain(fact["value"]["normalized"]) == plain(candidate.value.normalized)]
    if same:
        return "duplicate", same
    return ("conflict", [fact["item_id"] for fact in current]) if current else ("unverified", [])


def detail_of(lane, candidate: FactCandidate) -> str:
    """The quote and where it is, plus a note when the extractor was unsure."""
    record = lane.records.load("document", candidate.evidence.document_id) or {"title": "a removed document"}
    page = f", page {candidate.evidence.page}" if candidate.evidence.page else ""
    unsure = " Claude was unsure of this one." if "low_confidence" in candidate.flags else ""
    return f"“{stages_extract.quote_of(lane, candidate.evidence.model_dump())}” in {record['title']}{page}.{unsure}"


# --- S12 Librarian

def review_candidate(lane, envelope: Envelope) -> None:
    """S12: one review item per candidate, once. A duplicate is settled at once; everything else waits for a person."""
    candidate = FactCandidate.model_validate(envelope.payload)
    item_id = item_id_of(candidate.candidate_id)
    if lane.records.load(ITEM_KIND, item_id) or not lane.records.load(stages_extract.CANDIDATE_KIND, candidate.candidate_id):
        return  # a redelivery, or the document was erased since
    kind, fact_ids = classify(lane, candidate)
    lane.records.save(ITEM_KIND, item_id, LibrarianItem(
        item_id=item_id, kind=kind, title=candidate.statement, detail=detail_of(lane, candidate), candidate_id=candidate.candidate_id,
        document_id=candidate.evidence.document_id, fact_ids=fact_ids, status="resolved" if kind == "duplicate" else "open",
        resolution="duplicate" if kind == "duplicate" else None, created_at=lane.now))
    count(f"s12.{kind}")
    log_event("S12", "reviewed", candidate_id=candidate.candidate_id, kind=kind)
