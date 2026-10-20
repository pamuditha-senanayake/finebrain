# filing.py: step 14, S11 filing (B02, B03). Filing rules pick a document's type (its Library folder), how sensitive it is
# at least, and how long it is kept. Version chains: a document whose title differs only by a version, date or "final"
# joins the chain of the earlier one; the newest is current and the one before it is marked replaced, and its chunks stop
# answering "now" questions (their valid time ends; "as of" history still finds them).
# Used by: stages_file.py (S11), documents.py (Library view), lists.py (GET filing-rules), forget.py, vault_routes.py (start-up repair). Uses: nothing local.
import re
from datetime import datetime

from pydantic import BaseModel

# Config
# No type: an unmatched document keeps its file kind (md, pdf) as its type, as uploads did before step 14
FALLBACK_RULE = {"id": "uploads", "match": "anything else", "type": "", "sensitivity": "internal", "retention_days": 365}
CURRENT = {"done"}  # a chain's current version is its newest filed one; retired and erased ones never are
VERSION_WORDS = re.compile(r"\bv(?:ersion)?\s*\d+(?:\.\d+)*\b|\b(?:19|20)\d{2}(?:[-_/.]\d{1,2}){0,2}\b|\(\d+\)"
                           r"|\b(?:final|draft|copy|updated|latest|new|signed|rev(?:ision)?\s*\d*)\b")


class DocFiled(BaseModel):
    """docs.filed: S11 chose where a document lives."""
    document_id: str
    filing_rule: str
    doc_type: str
    domain: str
    sensitivity: str
    retention_days: int
    chain_id: str
    version: int


class DocExtracted(BaseModel):
    """docs.extracted: S11 finished reading a document into the search index."""
    document_id: str
    chunk_count: int
    characters: int


# --- Filing rules

def rules_of(seed: dict) -> list[dict]:
    """The tenant's rules in order, then the fallback that matches anything."""
    return [*seed.get("filing_rules", []), FALLBACK_RULE]


def rule_for(seed: dict, title: str, filename: str) -> dict:
    """The first rule whose pattern is found in the title or the file name, case ignored."""
    named = f"{title} {filename}".lower()
    for rule in seed.get("filing_rules", []):
        if re.search(rule["match"], named, re.IGNORECASE):
            return rule
    return FALLBACK_RULE


# --- Version chains

def chain_key(doc_type: str, title: str) -> str:
    """The title without version words, dates and punctuation, with its type: 'Refund policy v4' is 'policy:refund policy'."""
    words = title.lower().replace("_", " ")  # an underscore joins words in file names, so "policy_2026" hides its date otherwise
    stem = " ".join(re.sub(r"[^a-z0-9]+", " ", VERSION_WORDS.sub(" ", words)).split())
    return f"{doc_type}:{stem}" if stem else ""


def chain_for(records, document_id: str, key: str) -> tuple[str, int, str | None]:
    """The chain id, this document's version, and the current version it replaces (if any)."""
    members = [r for r in records.list_kind("document") if key and r.get("chain_key") == key and r["document_id"] != document_id]
    if not members:
        return document_id, 1, None
    first = min(members, key=lambda r: r.get("version", 1))
    current = [r for r in members if r["status"] in CURRENT]
    newest = max(current, key=lambda r: r.get("version", 1))["document_id"] if current else None
    return first.get("chain_id") or first["document_id"], max(r.get("version", 1) for r in members) + 1, newest


def replaced_by(records, record: dict) -> str | None:
    """The newer version that replaced this one, while that version is still filed; else None (this one is current)."""
    newer = record.get("superseded_by")
    later = records.load("document", newer) if newer else None
    return newer if later and later["status"] in CURRENT else None


# --- Replaced versions stop answering "now"

def retire_replaced(lane, document_id: str, when: datetime) -> int:
    """The replaced version's chunks end where the new version starts. Returns how many ended; ended ones are skipped."""
    live = [chunk["item_id"] for chunk in lane.chunks.of_document(document_id) if not chunk.get("valid_to")]
    for chunk_id in live:
        lane.chunks.retire(chunk_id, when)
    return len(live)


def reopen_replaced(lane, document_id: str) -> None:
    """The newer version was removed, so the version it replaced is current again, and so are its chunks."""
    for older in lane.records.list_kind("document"):
        if older.get("superseded_by") == document_id and older["status"] in CURRENT:
            for chunk in lane.chunks.of_document(older["document_id"]):
                lane.chunks.retire(chunk["item_id"], None)


def retire_all_replaced(lane) -> int:
    """Start-up repair: versions replaced before this rule kept answering "now". Safe to repeat."""
    ended = 0
    for older in lane.records.list_kind("document"):
        newer = replaced_by(lane.records, older)
        if newer:
            started = str(lane.records.load("document", newer)["uploaded_at"]).replace("Z", "+00:00")  # Python 3.10 cannot read a Z
            ended += retire_replaced(lane, older["document_id"], datetime.fromisoformat(started))
    return ended
