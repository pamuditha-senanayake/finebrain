# fact_commit.py: step 14 slice 3, settling a review item. Accept writes the candidate to main as a verified fact (a graph node
# through S14, so it has a version, a commit and a release that puts it in the search index); Reject closes the item and writes
# nothing. A conflict waits for slice 4's change request. Used by: api/vault_routes.py, tests. Uses: stages_librarian.py,
# stages_extract.py, stages_version.py, contracts_signal.py.
from app.pipeline import stages_extract, stages_librarian, stages_version
from app.pipeline.contracts_graph import CommitAuthor
from app.pipeline.contracts_signal import FactCandidate
from app.pipeline.stages_librarian import FACT_NODE, ITEM_KIND, LibrarianItem

# Config
ACCEPT_LEVEL = 2  # a new fact with its evidence is C2: one steward or leader (decision 2 of the step 14 plan)


class NotOpen(Exception):
    """The item was already settled, or it is a conflict, which needs a change request."""


def fact_id_of(candidate_id: str) -> str:
    return "fact_" + candidate_id.removeprefix("fc_")


def open_item(lane, item_id: str) -> LibrarianItem:
    """The item, if it can be settled here. LookupError when unknown; NotOpen when settled or a conflict."""
    stored = lane.records.load(ITEM_KIND, item_id)
    if stored is None:
        raise LookupError(item_id)
    item = LibrarianItem.model_validate(stored)
    if item.status != "open":
        raise NotOpen("already_settled")
    if item.kind == "conflict":
        raise NotOpen("conflict_needs_change_request")
    return item


def fact_fields(lane, candidate: FactCandidate, person: str) -> dict:
    """The fact as S5 reads it (a context item of kind fact), with its subject, value and evidence beside it."""
    record = lane.records.load("document", candidate.evidence.document_id)
    evidence = candidate.evidence.model_dump()
    return {
        "item_id": fact_id_of(candidate.candidate_id), "kind": "fact", "text": candidate.statement,
        "source": {"document_id": evidence["document_id"], "uri": record["original_uri"], "page": evidence["page"], "span": evidence["span"], "chunk_id": evidence["chunk_id"]},
        "valid_from": candidate.valid_from.isoformat() if candidate.valid_from else str(record["uploaded_at"]),  # else true since it arrived
        "valid_to": candidate.valid_to.isoformat() if candidate.valid_to else None, "recorded_at": lane.now.isoformat(),
        "verified_by": person, "version_ref": None, "score": 0.0, "sensitivity": candidate.sensitivity, "domain": record.get("domain", "general"),
        "subject": candidate.subject.model_dump(), "predicate": candidate.predicate, "value": candidate.value.model_dump(), "status": "verified",
        "evidence": [{**evidence, "quote": stages_extract.quote_of(lane, evidence)}], "candidate_id": candidate.candidate_id,
        "answers": next((flag.removeprefix("answers:") for flag in candidate.flags if flag.startswith("answers:")), None),  # step 16
    }


def settle(lane, item: LibrarianItem, resolution: str, person: str, fact_ids: list[str]) -> None:
    lane.records.save(ITEM_KIND, item.item_id, item.model_copy(update={
        "status": "resolved", "resolution": resolution, "decided_by": person, "decided_at": lane.now, "fact_ids": fact_ids}))


def accept(lane, item_id: str, person: str) -> str:
    """Write the candidate to main as a verified fact, and return its id."""
    item = open_item(lane, item_id)
    candidate = FactCandidate.model_validate(lane.records.load(stages_extract.CANDIDATE_KIND, item.candidate_id))
    fields = fact_fields(lane, candidate, person)
    draft = stages_version.Draft(op="add", node_type=FACT_NODE, node_id=fields["item_id"], fields=fields, base_version=0)
    message = f"Verify {fields['item_id']} from {candidate.evidence.document_id}"  # no words of the fact: commits outlive an erase
    stages_version.apply(lane, CommitAuthor(kind="human", id=person), message, [draft], ACCEPT_LEVEL)
    settle(lane, item, "accepted", person, [fields["item_id"]])
    stages_librarian.reclassify(lane, candidate.subject.entity_ref, candidate.predicate)  # a waiting claim may now be a conflict
    return fields["item_id"]


def reject(lane, item_id: str, person: str) -> None:
    """Close the item. The candidate stays on record, so the same claim is not asked again without a trace."""
    settle(lane, open_item(lane, item_id), "rejected", person, [])
