# documents.py: uploads from the console (Ask the Brain) and the Library list. An upload keeps the original file in S3,
# writes a pending Library record, then goes through S1 and S2 like any signal, so personal data is masked before S11
# files it as searchable knowledge. Used by: routes.py, tests/test_documents.py. Uses: extract.py, stages_file.py, capture_api.py.
import uuid
from datetime import datetime

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

from app.api import ui_models_graph as g
from app.pipeline import capture_api
from app.pipeline.extract import UnreadableFile, kind_of, text_of
from app.pipeline.stages_file import DocumentRecord
from app.pipeline.stages_normalize import UNSAFE_FILENAME

# Config
CONNECTOR_ID = "conn_upload_console"
LARGEST_UPLOAD = 10 * 1024 * 1024  # 10 MB
UPLOAD_SENSITIVITIES = {"public", "internal", "confidential", "restricted"}
RETENTION_DAYS = 365  # sample filing rule until open question 5 is answered


class Document(g.UiModel):
    id: str
    tenant_id: str
    cluster_id: str
    title: str
    source: str
    type: str
    sensitivity: str
    extraction_status: str
    linked_facts: list[str]
    retention_days: int
    filing_rule: str
    uploaded_by: str
    uploaded_at: str
    size_kb: int
    personal_data: bool


def document_view(lane, record: dict) -> dict:
    return Document(
        id=record["document_id"], tenant_id=lane.seed["tenant_id"], cluster_id=lane.seed["cluster_id"], title=record["title"], source="Ask the Brain upload",
        type=record["kind"].lstrip(".") or "file", sensitivity=record["sensitivity"], extraction_status=record["status"], linked_facts=[],
        retention_days=RETENTION_DAYS, filing_rule="uploads", uploaded_by=record["uploaded_by"], uploaded_at=str(record["uploaded_at"]),
        size_kb=max(1, record["size_bytes"] // 1024), personal_data=record["personal_data"],
    ).ui()


def documents_view(lane) -> list[dict]:
    """The Library: newest first."""
    return sorted((document_view(lane, record) for record in lane.records.list_kind("document")), key=lambda d: d["uploadedAt"], reverse=True)


def accept(lane, persona: str, filename: str, data: bytes, sensitivity: str) -> dict:
    """Store the original, record it as pending, and hand the text to S1. Raises HTTPException for a bad file."""
    if len(data) > LARGEST_UPLOAD:
        raise HTTPException(413, "too_large")
    if sensitivity not in UPLOAD_SENSITIVITIES:
        raise HTTPException(400, "unknown_sensitivity")
    try:
        text = text_of(filename, data)
    except UnreadableFile as error:
        raise HTTPException(415, str(error)) from None
    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    safe_name = UNSAFE_FILENAME.sub("_", filename)
    original_uri = f"s3://brain/{lane.seed['tenant_id']}/documents/{document_id}/{safe_name}"
    lane.object_store[original_uri] = data
    record = DocumentRecord(document_id=document_id, title=filename.rsplit(".", 1)[0].replace("_", " "), filename=safe_name, kind=kind_of(filename),
                            size_bytes=len(data), uploaded_by=persona, uploaded_at=lane.now, sensitivity=sensitivity, status="pending", original_uri=original_uri)
    lane.records.save("document", document_id, record)
    connector = lane.seed["connectors"][CONNECTOR_ID]
    raw = {"connector_id": CONNECTOR_ID, "grant_id": connector["grant_id"], "source_type": connector["source_type"], "external_id": document_id,
           "content_type": "text/plain", "raw_body": text, "headers_subset": {"filename": safe_name, "uploaded_by": persona}}
    capture_api.publish_or_503(lane, raw)
    return document_view(lane, lane.records.load("document", document_id))


def register(app: FastAPI, lane, check) -> None:
    """POST /api/t/{tenant}/documents: one file, multipart. Must be added before the catch-all POST route."""

    @app.post("/api/t/{tenant}/documents", status_code=202)
    async def upload(tenant: str, file: UploadFile = File(...), sensitivity: str = Form("internal"), x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        return accept(lane, x_persona, file.filename or "upload.txt", await file.read(), sensitivity)
