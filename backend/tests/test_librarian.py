# test_librarian.py: step 14 slice 3, S12 and the vault. Each candidate becomes one review item (unverified, duplicate, stale or
# conflict); Accept writes a verified fact through S14 that the vault lists and Ask can find by the thing's name; Reject writes
# nothing; forgetting the document takes its facts along. Uses: stages_librarian.py, fact_commit.py, vault_*.py, tests/test_extract.py.
from app.api import ask
from app.pipeline import stages_extract
from tests.test_documents import FOUNDER, TENANT
from tests.test_extract import FEE, NOTICE, answering, build, filed
from tests.test_forget import remove

# Config
STEWARD = "h-udayanga"
STALE = {**FEE, "predicate": "old_fee", "valid_to": "2020-01-31", "quote": "The monthly fee is LKR 40,000, paid within 30 days"}


# --- Helpers

def get(client, resource: str, persona: str = FOUNDER):
    return client.get(f"/api/t/{TENANT}/{resource}", headers={"x-persona": persona}).json()


def op(client, name: str, item_id: str, persona: str = FOUNDER):
    return client.post(f"/api/t/{TENANT}/ops/{name}", json={"itemId": item_id}, headers={"x-persona": persona})


def queue(client) -> dict[str, dict]:
    return {item["title"]: item for item in get(client, "librarian")}


def accepted_lane(*facts: dict):
    """A lane where the contract was filed and its first item accepted by the steward. Returns the client, lane and fact id."""
    client, lane = build(answering(*facts)[0])
    filed(client, lane)
    item = next(item for item in get(client, "librarian") if item["status"] == "open")
    fact_id = op(client, "librarianAccept", item["id"], STEWARD).json()["factId"]
    lane.bus.drain()  # the release puts the fact in the search index
    return client, lane, fact_id


# --- Review items

def test_each_candidate_becomes_one_open_item():
    client, lane = build(answering(FEE, NOTICE)[0])
    filed(client, lane)
    items = get(client, "librarian")
    assert len(items) == 2 and {(item["kind"], item["status"]) for item in items} == {("unverified", "open")}
    details = sorted(item["detail"] for item in items)
    assert details[1].startswith("“The monthly fee is LKR 40,000”") and "unsure" in details[0]


def test_a_fact_whose_validity_ended_is_stale():
    client, lane = build(answering(STALE)[0])
    filed(client, lane)
    assert [item["kind"] for item in get(client, "librarian")] == ["stale"]


def test_the_same_value_again_is_a_settled_duplicate_and_a_new_value_is_a_conflict():
    client, lane, fact_id = accepted_lane(FEE)
    lane.extract = answering(FEE, {**FEE, "quote": "Late delivery earns Finebase a credit", "value_normalized": "LKR 3800000"})[0]
    filed(client, lane, "Lanka Print supplier agreement v2.md")
    later = [item for item in get(client, "librarian") if item["factIds"] != [fact_id] or item["kind"] != "unverified"]
    kinds = {item["kind"]: item for item in later if item["kind"] in ("duplicate", "conflict")}
    assert kinds["duplicate"]["status"] == "resolved" and kinds["duplicate"]["factIds"] == [fact_id]
    assert kinds["conflict"]["status"] == "open" and kinds["conflict"]["factIds"] == [fact_id]
    assert op(client, "librarianAccept", kinds["conflict"]["id"]).status_code == 409  # slice 4 drafts its change request


# --- Accept and Reject

def test_accept_writes_a_verified_fact_the_vault_lists():
    client, lane, fact_id = accepted_lane(FEE)
    fact = next(f for f in get(client, "facts") if f["id"] == fact_id)
    assert (fact["status"], fact["verifiedBy"], fact["subject"], fact["value"]) == ("verified", STEWARD, "lanka print", "LKR 40,000")
    assert fact["evidence"][0]["quote"] == FEE["quote"] and fact["validFrom"].startswith("2026-10-01")
    assert lane.records.load("commit", lane.graph.history("fact", fact_id)[-1]["_ref"]["commit_id"])["criticality"] == 2
    assert op(client, "librarianAccept", next(iter(queue(client).values()))["id"]).status_code == 409  # settled once


def test_ask_finds_the_fact_by_the_suppliers_name():
    product = {**FEE, "subject_type": "product", "subject_name": "Printed user manuals", "parties": ["Lanka Print (Pvt) Ltd", "Finebase"]}
    client, lane, fact_id = accepted_lane(product)  # the fee is about the product; the supplier is only a party, as real Claude often answers
    bundle = ask.read_for(lane, FOUNDER, "What does Lanka Print charge each month?")
    assert fact_id in {item.item_id for item in bundle.items} and bundle.scope.level == "entity"


def test_reject_writes_nothing():
    client, lane = build(answering(FEE)[0])
    filed(client, lane)
    item = next(iter(queue(client).values()))
    assert op(client, "librarianReject", item["id"]).json()["ok"] is True
    assert queue(client)[FEE["statement"]]["status"] == "resolved" and not [f for f in get(client, "facts") if f["id"].startswith("fact_")]


def test_unknown_items_and_people_are_refused():
    client, _ = build(answering(FEE)[0])
    assert op(client, "librarianAccept", "li_nothing").status_code == 404
    assert op(client, "librarianAccept", "li_nothing", "h-stranger").status_code == 401


# --- Forgetting

def test_retiring_the_document_closes_its_facts():
    client, lane, fact_id = accepted_lane(FEE)
    remove(client, lane.records.list_kind("document")[0]["document_id"], "retire")
    assert fact_id not in {f["id"] for f in get(client, "facts")} and len(lane.graph.history("fact", fact_id)) == 2


def test_erasing_the_document_leaves_no_word_of_its_facts():
    client, lane, fact_id = accepted_lane(FEE)
    commit_id = lane.graph.history("fact", fact_id)[0]["_ref"]["commit_id"]
    remove(client, lane.records.list_kind("document")[0]["document_id"], "erase")
    assert get(client, "librarian") == [] and fact_id not in {f["id"] for f in get(client, "facts")}
    assert all("text" not in version for version in lane.graph.history("fact", fact_id))
    assert "40,000" not in str(lane.records.history("commit", commit_id)) and not lane.records.list_kind(stages_extract.CANDIDATE_KIND)
