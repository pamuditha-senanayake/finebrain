# test_lane_b.py: step 14's done check, end to end through the API. An uploaded contract is filed by its rule, its facts are
# proposed with exact quotes, a steward reviews each one, and the vault then holds them as verified facts with their proof,
# which Ask can find by the supplier's name. Uses: tests/test_extract.py and test_librarian.py (helpers), api/ask.py.
from app.api import ask
from tests.test_documents import TENANT
from tests.test_extract import FEE, answering, build, filed
from tests.test_librarian import STEWARD, get, op

# Config
START = {**FEE, "quote": "It starts on 1 October 2026", "statement": "The agreement starts on 1 October 2026.", "subject_type": "contract",
         "subject_name": "Supplier agreement", "predicate": "start_date", "value_type": "date", "value_raw": "1 October 2026", "value_normalized": "2026-10-01"}
NOTICE = {**FEE, "quote": "Either party may end this agreement with 60 days written notice", "statement": "Either party may end it with 60 days notice.",
          "subject_type": "contract", "subject_name": "Supplier agreement", "predicate": "notice_period", "value_type": "duration", "value_raw": "60 days",
          "value_normalized": "P60D", "parties": ["Lanka Print (Pvt) Ltd", "Finebase (Pvt) Ltd"]}


def test_an_uploaded_contract_becomes_reviewed_facts_in_the_vault():
    # Step 1: upload the contract; S11 files it as a contract and proposes three facts
    client, lane = build(answering(FEE, START, NOTICE)[0])
    document_id = filed(client, lane)
    document = next(d for d in get(client, "documents") if d["id"] == document_id)
    assert (document["type"], document["filingRule"]) == ("contract", "fr_contracts")
    waiting = [i for i in get(client, "librarian") if i["status"] == "open"]
    assert len(waiting) == 3 and {i["kind"] for i in waiting} == {"unverified"}

    # Step 2: a steward reviews each one
    for item in waiting:
        assert op(client, "librarianAccept", item["id"], STEWARD).json()["ok"] is True
        lane.bus.drain()  # as on real infra: each release indexes its fact before the next accept
    assert not [i for i in get(client, "librarian") if i["status"] != "resolved"]

    # Step 3: the vault holds them, verified, each with its quote from this document
    facts = {f["statement"]: f for f in get(client, "facts") if f["id"].startswith("fact_")}
    assert set(facts) == {FEE["statement"], START["statement"], NOTICE["statement"]}
    assert all(f["status"] == "verified" and f["verifiedBy"] == STEWARD and f["evidence"][0]["documentId"] == document_id for f in facts.values())
    assert facts[NOTICE["statement"]]["evidence"][0]["quote"] == NOTICE["quote"]
    text = client.get(f"/api/t/{TENANT}/documents/{document_id}/chunks", headers={"x-persona": STEWARD}).json()
    assert text and not any(chunk["id"].startswith("fact_") for chunk in text)  # the Library shows the document, not its facts

    # Step 4: Ask finds them by the supplier's name
    found = {item.item_id for item in ask.read_for(lane, STEWARD, "How much notice does Lanka Print need?").items}
    assert {fact["id"] for fact in facts.values()} & found
