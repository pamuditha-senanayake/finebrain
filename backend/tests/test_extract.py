# test_extract.py: step 14 slice 2, S11 fact extraction: real quotes only, exact spans, registry subjects, unsure flags; a stand-in
# replaces Claude. Uses: stages_extract.py, fact_prompt.py, stages_file.py, entity_match.py, tests/test_documents.py, test_forget.py.
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import create_api_app
from app.pipeline import fakes, orchestrate, stages_extract
from app.pipeline.entity_match import entity_id_of
from app.pipeline.stages_file import index_chunks
from tests.golden import NOW
from tests.test_documents import FOUNDER, HQ, SEED, TENANT, upload
from tests.test_forget import remove

# Config
CONTRACT = (Path(__file__).resolve().parents[1] / "samples" / "sample_supplier_contract.md").read_bytes()
FEE = {"quote": "The monthly fee is LKR 40,000", "statement": "Lanka Print's monthly fee is LKR 40,000.", "subject_type": "organization",
       "subject_name": "Lanka Print (Pvt) Ltd", "predicate": "monthly_fee", "value_type": "money", "value_raw": "LKR 40,000",
       "value_normalized": "LKR 4000000", "valid_from": "2026-10-01", "valid_to": "2027-09-30", "confidence": 0.95}
NOTICE = {**FEE, "quote": "Either party may end this agreement with 60 days written notice", "predicate": "notice_period",
          "subject_type": "contract", "subject_name": "Supplier agreement", "value_type": "duration", "value_normalized": "P60D", "confidence": 0.4}
INVENTED = {**FEE, "quote": "The monthly fee is LKR 90,000", "predicate": "invented_fee"}


# --- Helpers

def answering(*facts: dict):
    """A Claude stand-in that records these facts, naming the first part, whatever it is asked. Returns it and its calls."""
    calls = []

    def extract(system: str, messages: list[dict], tools: list[dict]):
        calls.append(messages)
        first = messages[0]["content"].split('<part id="')[1].split('"')[0]
        block = SimpleNamespace(type="tool_use", name="record_facts", input={"facts": [{**fact, "part": first} for fact in facts]})
        return SimpleNamespace(model="claude-haiku-5-5", content=[block])

    return extract, calls


def build(extract):
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, extract=extract)
    return TestClient(create_api_app(lane, HQ)), lane


def filed(client, lane, name: str = "Lanka Print supplier agreement.md", data: bytes = CONTRACT) -> str:
    document_id = upload(client, name, data).json()["id"]
    lane.bus.drain()
    return document_id


def candidates(lane) -> list[dict]:
    return lane.records.list_kind(stages_extract.CANDIDATE_KIND)


# --- Extraction

def test_a_fact_with_a_real_quote_becomes_a_candidate_with_its_exact_span():
    client, lane = build(answering(FEE)[0])
    document_id = filed(client, lane)
    [candidate] = candidates(lane)
    chunk = next(c for c in client.get(f"/api/t/{TENANT}/documents/{document_id}/chunks", headers={"x-persona": FOUNDER}).json() if c["id"] == candidate["evidence"]["chunk_id"])
    start, end = map(int, candidate["evidence"]["span"].split(":"))
    assert chunk["text"][start:end] == FEE["quote"] and candidate["value"]["normalized"] == "LKR 4000000"
    assert candidate["valid_from"].startswith("2026-10-01") and candidate["flags"] == []
    assert lane.bus.topics["facts.candidates"][-1].payload["candidate_id"] == candidate["candidate_id"]


def test_the_subject_is_one_entity_whatever_its_company_ending():
    client, lane = build(answering(FEE, {**FEE, "subject_name": "Lanka Print", "predicate": "payment_terms"})[0])
    filed(client, lane)
    subjects = {c["subject"]["entity_ref"] for c in candidates(lane)}
    assert subjects == {entity_id_of("organization", "lanka print")} and lane.entities.get(subjects.pop())["type"] == "organization"


def test_a_payment_subject_needs_a_payment_reference():
    client, lane = build(answering({**FEE, "subject_type": "payment", "subject_name": "Lanka Print monthly fee"})[0])
    filed(client, lane)
    assert candidates(lane)[0]["subject"] == {"entity_type": "other", "entity_ref": "Lanka Print monthly fee"}
    assert not [e for e in lane.entities.all() if e["type"] == "payment"]


def test_an_invented_quote_is_dropped():
    client, lane = build(answering(FEE, INVENTED)[0])
    document_id = filed(client, lane)
    assert [c["predicate"] for c in candidates(lane)] == ["monthly_fee"]
    assert lane.records.load(stages_extract.EXTRACTION_KIND, document_id)["dropped"] == 1


def test_an_unsure_fact_is_flagged_for_the_librarian():
    client, lane = build(answering(NOTICE)[0])
    filed(client, lane)
    assert candidates(lane)[0]["flags"] == ["low_confidence"]


def test_a_redelivery_proposes_nothing_twice():
    extract, calls = answering(FEE)
    client, lane = build(extract)
    filed(client, lane)
    for envelope in list(lane.bus.topics["docs.extracted"]):
        stages_extract.extract_document(lane, envelope)
    assert len(candidates(lane)) == 1 and len(calls) == 1


def test_without_a_model_the_document_is_filed_and_no_fact_is_invented():
    client, lane = build(None)
    document_id = filed(client, lane)
    assert candidates(lane) == [] and lane.records.load(stages_extract.EXTRACTION_KIND, document_id)["status"] == "skipped"


def test_an_outage_leaves_the_document_filed_and_the_message_for_replay():
    def down(system, messages, tools):
        raise ConnectionError("model down")
    client, lane = build(down)
    document_id = filed(client, lane)
    assert lane.records.load("document", document_id)["status"] == "done" and candidates(lane) == []
    assert lane.records.load(stages_extract.EXTRACTION_KIND, document_id) is None  # not marked done, so a replay extracts it


def test_erasing_the_document_removes_its_candidates():
    client, lane = build(answering(FEE)[0])
    document_id = filed(client, lane)
    answer = remove(client, document_id, "erase")
    assert next(layer for layer in answer["receipt"]["layers"] if layer["layer"] == "Facts")["result"] == "cleared"
    assert candidates(lane) == [] and lane.records.load(stages_extract.EXTRACTION_KIND, document_id) is None
    assert any(e["action"] == "forget.completed" for e in client.get(f"/api/t/{TENANT}/audit", headers={"x-persona": FOUNDER}).json())  # its plain entry reads


def test_a_span_knows_its_page_from_page_breaks():
    parts = [{"id": "d_c1", "text": "Page one.\f"}, {"id": "d_c2", "text": "Page two.\fPage three says the fee."}]
    assert stages_extract.page_of(parts, 1, parts[1]["text"].index("Page three")) == 3
    assert stages_extract.page_of([{"id": "d_c1", "text": "No pages here."}], 0, 3) is None


def test_a_rate_limited_embedding_is_tried_again():
    _, lane = build(None)
    tries = []

    class RateLimited(Exception):
        retryable = True

    def flaky(texts, kind):
        tries.append(1)
        if len(tries) == 1:
            raise RateLimited("429")
        return fakes.fake_embed(texts, kind)

    lane.embed = flaky
    record = SimpleNamespace(document_id="doc_x", title="Note", original_uri="s3://x", uploaded_at=NOW)
    assert len(index_chunks(lane, record, "One paragraph.", "internal", "general")) == 1 and len(tries) == 2
