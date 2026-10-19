# test_ready_evidence.py: step 16 slice 3, evidence closes the gap. A file uploaded to a request is filed with what it was asked
# for, extraction is told so, a person accepts the fact in the Vault, and the request is fulfilled; retiring the file reopens it.
# A stand-in replaces Claude. Uses: ready_routes.py, stages_ready.py, fact_prompt.py, tests/test_extract.py, test_librarian.py, test_forget.py.
from app.pipeline import stages_ready
from tests.test_documents import FOUNDER, TENANT
from tests.test_extract import FEE, answering, build
from tests.test_forget import remove
from tests.test_librarian import get, op

# Config
REQUEST = "er_ob_vat_2026_09_input_invoices"
INVOICES = b"Input VAT invoices\n\nTotal input VAT for September 2026 is LKR 380,000, across 14 supplier invoices."
VAT = {**FEE, "quote": "Total input VAT for September 2026 is LKR 380,000", "statement": "Input VAT for September 2026 is LKR 380,000.",
       "subject_type": "organization", "subject_name": "Finebase", "predicate": "total_input_vat", "value_raw": "LKR 380,000",
       "value_normalized": "LKR 38000000", "valid_from": "2026-09-01", "valid_to": None, "proves_request": True}  # as real Claude answers: its own predicate name


# --- Helpers

def uploaded(client, lane, request_id: str = REQUEST, data: bytes = INVOICES):
    get(client, "gaps")  # the first read runs the check, which opens the requests
    answer = client.post(f"/api/t/{TENANT}/evidence-requests/{request_id}/upload", files={"file": ("september_input_invoices.md", data)}, headers={"x-persona": FOUNDER})
    lane.bus.drain()
    return answer


def request_of(client) -> dict:
    return next(r for r in get(client, "evidence-requests") if r["id"] == REQUEST)


def vat(client) -> dict:
    return next(o for o in get(client, "obligations") if o["id"] == "ob_vat:2026-09")


def accept_the_fact(client, lane) -> None:
    item = next(i for i in get(client, "librarian") if i["status"] == "open")
    assert op(client, "librarianAccept", item["id"]).json()["ok"] is True
    lane.bus.drain()


# --- The loop

def test_an_upload_is_filed_with_what_it_was_asked_for_and_extraction_is_told():
    extract, calls = answering(VAT)
    client, lane = build(extract)
    document_id = uploaded(client, lane).json()["id"]
    asked = lane.records.load("document", document_id)["evidence_for"]
    assert (asked["request_id"], asked["predicate"], asked["period"]) == (REQUEST, "vat_input_invoices", "2026-09")
    prompt = calls[0][0]["content"]
    assert "uploaded as evidence for: Input VAT invoices" in prompt and "proves_request" in prompt and "2026-09" in prompt
    assert [c["flags"] for c in lane.records.list_kind("fact_candidate")] == [[f"answers:{REQUEST}"]]


def test_accepting_the_fact_fulfils_the_request_and_closes_the_gap():
    client, lane = build(answering(VAT)[0])
    uploaded(client, lane)
    assert request_of(client)["status"] == "open" and vat(client)["readiness"] == 0  # nothing counts before a person accepts it
    accept_the_fact(client, lane)
    assert request_of(client)["status"] == "fulfilled" and vat(client)["readiness"] == 50
    assert "gap_ob_vat_2026_09_input_invoices" not in {g["id"] for g in get(client, "gaps")}


def test_retiring_the_evidence_reopens_the_gap():
    client, lane = build(answering(VAT)[0])
    document_id = uploaded(client, lane).json()["id"]
    accept_the_fact(client, lane)
    assert request_of(client)["status"] == "fulfilled"
    remove(client, document_id, "retire")
    assert request_of(client)["status"] == "open" and vat(client)["readiness"] == 0
    assert "gap_ob_vat_2026_09_input_invoices" in {g["id"] for g in get(client, "gaps")}
    assert [e["topic"] for e in lane.audit.in_order() if e["topic"] in ("evidence.fulfilled", "evidence.open")] == ["evidence.fulfilled", "evidence.open"]


# --- What is refused

def test_an_unknown_or_answered_request_takes_no_upload():
    client, lane = build(answering(VAT)[0])
    assert uploaded(client, lane, "er_nothing").status_code == 404
    uploaded(client, lane)
    accept_the_fact(client, lane)
    assert uploaded(client, lane).status_code == 409 and lane.records.load(stages_ready.REQUEST_KIND, REQUEST)["status"] == "fulfilled"
