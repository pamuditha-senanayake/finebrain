# test_filing.py: step 14 slice 1, S11 filing. Rules give a document its type, a sensitivity that is never lowered, and its
# retention; a new version of a document joins its chain and replaces the current one; docs.filed and docs.extracted announce it.
# Uses: app/pipeline/filing.py, stages_file.py, api/documents.py, lists.py, tests/test_documents.py and test_forget.py (helpers).
import pytest

from app.pipeline import filing
from tests.test_documents import FOUNDER, SEED, TENANT, build, upload
from tests.test_forget import remove

# Config
CONTRACT = b"Supplier agreement\n\nLanka Print supplies printed manuals to Finebase at LKR 40,000 a month."
POLICY = b"Refund policy\n\nCustomers may ask for a refund within 30 days."


# --- Helpers

def filed(client, lane, name: str, data: bytes, sensitivity: str = "internal") -> dict:
    document_id = upload(client, name, data, sensitivity).json()["id"]
    lane.bus.drain()
    return shown(client, document_id)


def shown(client, document_id: str) -> dict:
    return next(d for d in client.get(f"/api/t/{TENANT}/documents", headers={"x-persona": FOUNDER}).json() if d["id"] == document_id)


# --- Rules

def test_a_contract_is_filed_by_its_rule():
    client, lane = build()
    document = filed(client, lane, "Lanka Print supplier agreement.md", CONTRACT)
    assert (document["type"], document["filingRule"], document["retentionDays"], document["sensitivity"]) == ("contract", "fr_contracts", 2555, "confidential")


def test_a_rule_never_lowers_what_the_uploader_chose():
    client, lane = build()
    assert filed(client, lane, "agreement.md", CONTRACT, "restricted")["sensitivity"] == "restricted"


def test_an_unmatched_name_takes_the_fallback():
    client, lane = build()
    document = filed(client, lane, "notes.md", b"Notes\n\nNothing special.")
    assert (document["filingRule"], document["type"], document["retentionDays"]) == ("uploads", "md", 365)  # it keeps its file kind


def test_filing_rules_are_served_in_order_ending_with_the_fallback():
    client, _ = build()
    rules = client.get(f"/api/t/{TENANT}/filing-rules", headers={"x-persona": FOUNDER}).json()
    assert [rule["id"] for rule in rules] == [rule["id"] for rule in SEED["filing_rules"]] + ["uploads"]
    assert set(rules[0]) == {"id", "match", "clusterId", "type", "sensitivity", "retentionDays"}


# --- Version chains

@pytest.mark.parametrize("title, stem", [("Refund policy v4", "policy:refund policy"), ("Refund_Policy_2026-10 final", "policy:refund policy"),
                                         ("Refund policy (2)", "policy:refund policy"), ("v2", "")])
def test_a_title_without_its_version_words_is_the_chain_key(title, stem):
    assert filing.chain_key("policy", title) == stem


def test_a_new_version_joins_the_chain_and_replaces_the_current_one():
    client, lane = build()
    first = filed(client, lane, "Refund policy v3.md", POLICY)
    second = filed(client, lane, "Refund policy v4.md", POLICY.replace(b"30", b"45"))
    assert (first["version"], second["version"]) == (1, 2)
    assert shown(client, first["id"])["replacedBy"] == second["id"] and second["replacedBy"] is None


def test_other_documents_start_their_own_chain():
    client, lane = build()
    filed(client, lane, "Refund policy v3.md", POLICY)
    assert filed(client, lane, "Leave policy.md", b"Leave policy\n\nTwenty days a year.")["version"] == 1


def test_removing_the_newer_version_makes_the_older_current_again():
    client, lane = build()
    first = filed(client, lane, "Refund policy v3.md", POLICY)
    second = filed(client, lane, "Refund policy v4.md", POLICY)
    remove(client, second["id"], "erase")
    assert shown(client, first["id"])["replacedBy"] is None
    assert filed(client, lane, "Refund policy v5.md", POLICY)["version"] == 2  # numbering follows the versions still filed


# --- Events

def test_filing_is_announced():
    client, lane = build()
    document = filed(client, lane, "Lanka Print supplier agreement.md", CONTRACT)
    placed = lane.bus.topics["docs.filed"][-1].payload
    done = lane.bus.topics["docs.extracted"][-1].payload
    assert (placed["document_id"], placed["doc_type"], placed["version"]) == (document["id"], "contract", 1)
    assert done["document_id"] == document["id"] and done["chunk_count"] >= 1 and done["characters"] > 0
