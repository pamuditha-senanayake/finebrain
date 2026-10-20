# vault_views.py: step 14 slice 3, the Ground truth vault for the console: verified facts with their evidence, and the
# librarian's review queue. Shapes copy the console's Fact and LibrarianItem (contracts/knowledge.ts).
# Used by: lists.py (GET facts, GET librarian), tests. Uses: ui_models_graph.py (UiModel), stages_librarian.py, studio_changes.py (ChangeRecord).
from app.api import ui_models_graph as g
from app.api.studio_changes import ChangeRecord
from app.pipeline.field_dictionary import core_of
from app.pipeline.stages_librarian import FACT_NODE, ITEM_KIND


class FactEvidence(g.UiModel):
    document_id: str
    page: int | None
    quote: str


class FactDependent(g.UiModel):
    type: str
    id: str
    label: str


class Fact(g.UiModel):
    id: str
    tenant_id: str
    cluster_id: str
    statement: str
    subject: str
    value: str
    valid_from: str
    valid_to: str | None
    recorded_at: str
    evidence: list[FactEvidence]
    verified_by: str | None
    status: str
    sensitivity: str
    dependents: list[FactDependent]
    core: dict | None = None  # step 13d: who, what, when, amount, outcome (field_dictionary.py)
    extra: dict | None = None


class LibrarianItem(g.UiModel):
    id: str
    kind: str
    title: str
    detail: str
    fact_ids: list[str]
    policy_id: str | None
    document_id: str | None
    proposal: dict | None
    status: str
    change_request_id: str | None
    created_at: str


# --- Facts

def subject_label(lane, fact: dict) -> str:
    """The thing a fact is about, by its name in the registry; a seed fact has none, so its id stands in."""
    ref = (fact.get("subject") or {}).get("entity_ref", "")
    entity = lane.entities.get(ref) if ref.startswith("ent_") else None
    return entity["key"] if entity else ref or fact["item_id"]


def evidence_of(fact: dict) -> list[FactEvidence]:
    """Verified facts carry their quotes; a seed fact points at its source document, and its own text is the quote."""
    if fact.get("evidence"):
        return [FactEvidence(document_id=e["document_id"], page=e.get("page"), quote=e.get("quote", "")) for e in fact["evidence"]]
    return [FactEvidence(document_id=fact["source"]["document_id"], page=fact["source"].get("page"), quote=fact["text"])]


def fact_view(lane, fact: dict) -> dict:
    value = fact.get("value") or {}
    return Fact(id=fact["item_id"], tenant_id=lane.seed["tenant_id"], cluster_id=lane.seed["cluster_id"], statement=fact["text"], subject=subject_label(lane, fact),
                value=value.get("raw") or value.get("normalized") or "", valid_from=str(fact.get("valid_from") or fact["recorded_at"]), valid_to=fact.get("valid_to"),
                recorded_at=str(fact["recorded_at"]), evidence=evidence_of(fact), verified_by=fact.get("verified_by"), status=fact.get("status", "verified"),
                sensitivity=fact["sensitivity"], dependents=[], **core_of(fact, subject_label(lane, fact))).ui()


def facts_view(lane) -> list[dict]:
    """Every fact true on main: those people verified, and the seed's own facts. Newest first."""
    facts = lane.graph.latest(FACT_NODE) + [item for item in lane.graph.latest("knowledge") if item.get("kind") == "fact"]
    return sorted((fact_view(lane, fact) for fact in facts), key=lambda shown: shown["recordedAt"], reverse=True)


# --- The review queue

def status_of(lane, item: dict) -> str:
    """A proposed item is settled once its change request is: merged, rejected or blocked by a conflict."""
    if item["status"] != "proposed":
        return item["status"]
    stored = lane.records.load("change_request", item.get("change_request_id") or "")
    return "proposed" if stored is None or ChangeRecord.model_validate(stored).status in ("awaiting_approval", "approved") else "resolved"


def proposal_of(item: dict) -> dict | None:
    """Which source wins, from when, and what relied on the current fact, in the console's shape."""
    p = item.get("proposal")
    return {"winningSource": p["winningSource"], "newValidFrom": p["newValidFrom"], "dependents": p["dependents"]} if p else None


def librarian_view(lane) -> list[dict]:
    """The librarian's items, open ones first, then newest first."""
    items = sorted(lane.records.list_kind(ITEM_KIND), key=lambda item: str(item["created_at"]), reverse=True)
    items = sorted(items, key=lambda item: item["status"] != "open")
    return [LibrarianItem(id=item["item_id"], kind=item["kind"], title=item["title"], detail=item["detail"], fact_ids=item["fact_ids"], policy_id=None,
                          document_id=item["document_id"], proposal=proposal_of(item), status=status_of(lane, item), change_request_id=item.get("change_request_id"),
                          created_at=str(item["created_at"])).ui() for item in items]
