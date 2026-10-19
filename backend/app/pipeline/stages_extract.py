# stages_extract.py: step 14 slice 2, S11 fact extraction (B06, B07). Once a document is indexed, Claude reads its parts and
# proposes facts. A fact is kept only when its quote is found word for word in the text; it becomes a K12 candidate on
# facts.candidates with its exact span, its page, and a subject in the entity registry. Nothing is saved until every call answered.
# Used by: orchestrate.py (consumer of docs.extracted). Uses: fact_prompt.py, entity_match.py, contracts_signal.py, observe.py.
import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel

from app.pipeline import entity_match, fact_prompt
from app.pipeline.contracts_signal import Envelope, Evidence, Extractor, FactCandidate, FactValue, Subject
from app.pipeline.observe import count, log_event

# Config
LOW_CONFIDENCE = 0.6  # below this a candidate goes to the librarian as unverified (failure rule K12)
PAGE_BREAK = "\f"  # extract.py puts one between PDF pages, so a span knows its page
CANDIDATE_KIND, EXTRACTION_KIND = "fact_candidate", "fact_extraction"


class ExtractionRecord(BaseModel):
    """What extraction did for one document: done, or skipped when no model is set."""
    document_id: str
    status: str
    candidates: int
    dropped: int  # facts whose quote was not found in the text
    model_id: str
    at: datetime


# --- Reading the document

def parts_of(lane, record: dict) -> list[dict]:
    """The document's chunks in order, without the title S11 puts in front, as the Library shows them."""
    prefix = f"{record['title']}: "
    bodies = sorted(lane.chunks.of_document(record["document_id"]), key=lambda body: int(body["item_id"].rsplit("_c", 1)[-1]))
    return [{"id": body["item_id"], "text": body["text"].removeprefix(prefix)} for body in bodies]


def quote_of(lane, evidence: dict) -> str:
    """The words a span points at, read back from the document's chunk. Empty when the chunk is gone."""
    record = lane.records.load("document", evidence["document_id"]) or {"title": "", "document_id": evidence["document_id"]}
    part = next((p for p in parts_of(lane, record) if p["id"] == evidence.get("chunk_id")), None)
    start, end = map(int, evidence["span"].split(":"))
    return part["text"][start:end] if part else ""


def locate(fact: dict, parts: list[dict]) -> tuple[int, int] | None:
    """(part index, start) of the quote: in the part Claude named, else in any part. None when it is nowhere: an invented quote."""
    quote = str(fact.get("quote", "")).strip()
    named = [i for i, part in enumerate(parts) if part["id"] == fact.get("part")]
    for i in named + [i for i in range(len(parts)) if i not in named]:
        start = parts[i]["text"].find(quote) if quote else -1
        if start >= 0:
            return i, start
    return None


def page_of(parts: list[dict], index: int, start: int) -> int | None:
    """The page a span starts on, counted from page breaks before it. None for files without pages."""
    if not any(PAGE_BREAK in part["text"] for part in parts):
        return None
    before = "".join(part["text"] for part in parts[:index]) + parts[index]["text"][:start]
    return before.count(PAGE_BREAK) + 1


def day(text) -> datetime | None:
    """A YYYY-MM-DD date as the start of that day in UTC, or None when there is none or it does not parse."""
    try:
        return datetime.fromisoformat(str(text)[:10]).replace(tzinfo=timezone.utc) if text else None
    except ValueError:
        return None


# --- Building a candidate

def note_mentioned(lane, entity_type: str, name: str, document_id: str, source: str) -> str | None:
    """Note a thing the document names and link the document to it, so a question naming it reaches this document."""
    entity_id = entity_match.note_named(lane.entities, entity_type, name, source, lane.now)
    if entity_id:
        lane.entities.link(entity_match.entity_id_of("document", document_id), "mentions", entity_id, source, lane.now)
    return entity_id


def subject_of(lane, fact: dict, document_id: str, source: str) -> Subject:
    """The thing the fact is about, and every party it involves, noted and linked from the document. An unnamed thing stays 'other'."""
    for party in fact.get("parties") or []:
        note_mentioned(lane, "organization", str(party), document_id, source)
    entity_id = note_mentioned(lane, fact.get("subject_type", "other"), str(fact.get("subject_name", "")), document_id, source)
    if entity_id is None:
        return Subject(entity_type="other", entity_ref=str(fact.get("subject_name", "")))
    return Subject(entity_type=fact["subject_type"], entity_ref=entity_id)


def candidate_of(lane, record: dict, fact: dict, parts: list[dict], found: tuple[int, int], model_id: str) -> FactCandidate:
    """One K12 candidate. Its id comes from where its quote is, so a second pass finds the same candidate."""
    index, start = found
    quote, part = str(fact["quote"]).strip(), parts[index]
    document_id, source = record["document_id"], entity_match.document_source(lane.seed["tenant_id"], record["document_id"])
    confidence = min(max(float(fact.get("confidence", 0)), 0.0), 1.0)
    evidence = Evidence(document_id=document_id, page=page_of(parts, index, start), span=f"{start}:{start + len(quote)}",
                        quote_sha256=hashlib.sha256(quote.encode()).hexdigest(), chunk_id=part["id"])
    return FactCandidate(
        candidate_id="fc_" + hashlib.sha256(f"{part['id']}|{start}|{fact.get('predicate')}".encode()).hexdigest()[:16],
        statement=str(fact.get("statement", quote)), subject=subject_of(lane, fact, document_id, source), predicate=str(fact.get("predicate", "states")),
        value=FactValue(type=str(fact.get("value_type", "text")), raw=str(fact.get("value_raw", "")), normalized=str(fact.get("value_normalized", ""))),
        valid_from=day(fact.get("valid_from")), valid_to=day(fact.get("valid_to")), evidence=evidence,
        extractor=Extractor(model_id=model_id, confidence=confidence), sensitivity=record["sensitivity"],
        flags=["low_confidence"] if confidence < LOW_CONFIDENCE else [],
    )


# --- S11 extraction

def ask(lane, record: dict, parts: list[dict]) -> tuple[list[dict], str]:
    """Every fact Claude records, window by window, and the model that answered. An outage raises, so the message is retried."""
    facts, model_id = [], "unknown"
    for window in fact_prompt.windows(parts):
        reply = lane.extract(fact_prompt.SYSTEM, fact_prompt.prompt(record["title"], window), [fact_prompt.TOOL])
        facts += fact_prompt.facts_in(reply)
        model_id = getattr(reply, "model", model_id)
    return facts, model_id


def extract_document(lane, envelope: Envelope) -> None:
    """S11: propose facts for a filed document, once. A redelivery, a removed document or no model does nothing more."""
    record = lane.records.load("document", envelope.payload["document_id"])
    if record is None or record["status"] != "done" or lane.records.load(EXTRACTION_KIND, record["document_id"]):
        return
    if lane.extract is None:
        lane.records.save(EXTRACTION_KIND, record["document_id"], ExtractionRecord(document_id=record["document_id"], status="skipped", candidates=0, dropped=0, model_id="none", at=lane.now))
        return

    # Step 1: ask, then keep only facts whose quote is in the text
    parts = parts_of(lane, record)
    facts, model_id = ask(lane, record, parts)
    found = [(fact, where) for fact in facts if (where := locate(fact, parts)) is not None]

    # Step 2: each kept fact becomes a candidate, saved and published once
    candidates = list({c.candidate_id: c for c in (candidate_of(lane, record, fact, parts, where, model_id) for fact, where in found)}.values())
    for candidate in candidates:
        lane.records.save(CANDIDATE_KIND, candidate.candidate_id, candidate)
        lane.bus.publish("facts.candidates", "fact.candidate", candidate, "ingest", envelope)
    lane.records.save(EXTRACTION_KIND, record["document_id"], ExtractionRecord(document_id=record["document_id"], status="done", candidates=len(candidates),
                      dropped=len(facts) - len(found), model_id=model_id, at=lane.now))
    count("s11.facts_dropped", len(facts) - len(found))
    log_event("S11", "facts_extracted", document_id=record["document_id"], candidates=len(candidates), dropped=len(facts) - len(found))
