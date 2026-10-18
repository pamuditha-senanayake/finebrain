# test_documents.py: uploads through the console API: text, Markdown and Word are read, personal data is masked by S2,
# S11 files the text as searchable knowledge, the Library lists it, and Ask the Brain can answer from it.
# Uses: app/api/documents.py, extract.py, stages_file.py, routes.py, hq.py (load_hq), orchestrate.py, tests/golden.py.
import io

import pytest
from docx import Document as WordDocument
from fastapi.testclient import TestClient

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import fakes, orchestrate
from app.pipeline.stages_file import CHUNK_CHARS, chunks_of
from tests.golden import NOW

# Config
SEED, HQ = load_hq()
TENANT = SEED["tenant_id"]
FOUNDER = "h-pamuditha"
NOTE = b"Support hours\n\nOur support team answers from 8 am to 6 pm, Monday to Saturday. Write to help@finebase.lk for anything urgent."


# --- Helpers

def build(answerer=None):
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    return TestClient(create_api_app(lane, HQ, answerer)), lane


def upload(client, name: str, data: bytes, sensitivity: str = "internal"):
    return client.post(f"/api/t/{TENANT}/documents", files={"file": (name, data)}, data={"sensitivity": sensitivity}, headers={"x-persona": FOUNDER})


def word_file(text: str) -> bytes:
    document, out = WordDocument(), io.BytesIO()
    document.add_paragraph(text)
    document.save(out)
    return out.getvalue()


# --- Upload to Library

def test_upload_is_masked_filed_and_listed():
    client, lane = build()
    accepted = upload(client, "support_hours.md", NOTE)
    assert accepted.status_code == 202 and accepted.json()["extractionStatus"] == "pending"
    lane.bus.drain()
    library = client.get(f"/api/t/{TENANT}/documents", headers={"x-persona": FOUNDER}).json()
    assert [(d["title"], d["extractionStatus"], d["type"]) for d in library] == [("support hours", "done", "md")]
    chunks = [node for node in lane.graph.latest("knowledge") if node["source"]["document_id"] == library[0]["id"]]
    assert chunks and "help@finebase.lk" not in chunks[0]["text"] and "8 am to 6 pm" in chunks[0]["text"]
    assert library[0]["personalData"] is True


def test_ask_answers_from_an_uploaded_document():
    seen = []

    def answerer(question, documents, history=(), address="sir"):
        seen.extend(item_id for item_id, _ in documents)
        return "From 8 am to 6 pm, sir.", [item_id for item_id, _ in documents if item_id.startswith("doc_")]

    client, lane = build(answerer)
    upload(client, "support_hours.txt", NOTE)
    lane.bus.drain()
    body = client.post(f"/api/t/{TENANT}/ask", json={"question": "What are the support hours?"}, headers={"x-persona": FOUNDER}).json()
    assert any(item.startswith("doc_") for item in seen)
    assert body["citations"] and body["citations"][0]["id"].startswith("doc_")


def test_word_files_are_read():
    client, lane = build()
    assert upload(client, "refund_note.docx", word_file("Refunds for annual plans are pro rata.")).status_code == 202
    lane.bus.drain()
    assert any("pro rata" in node["text"] for node in lane.graph.latest("knowledge"))


@pytest.mark.parametrize("name, data, status, error", [
    ("tool.exe", b"MZ", 415, "unsupported_type:.exe"),
    ("broken.pdf", b"not a pdf", 415, "broken_file"),
    ("empty.txt", b"   ", 415, "no_text"),
])
def test_bad_files_are_refused(name, data, status, error):
    client, _ = build()
    assert upload(client, name, data).json() == {"error": error}


def test_unknown_sensitivity_is_refused():
    client, _ = build()
    assert upload(client, "a.txt", b"hello", sensitivity="top_secret").status_code == 400


def test_chunks_keep_paragraphs_and_size():
    text = "\n\n".join(["short paragraph"] * 3 + ["x" * (CHUNK_CHARS + 10)])
    chunks = chunks_of(text)
    assert chunks[0].startswith("short paragraph") and all(len(chunk) <= CHUNK_CHARS for chunk in chunks)
