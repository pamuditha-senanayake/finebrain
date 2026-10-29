# documents.py: uploads from the console (Lisena) and the Library list. An upload keeps the original file in S3,
# writes a pending Library record, then goes through S1 and S2 like any signal, so personal data is masked before S11
# files it as searchable knowledge. Used by: routes.py, lists.py (filing rules), tests/test_documents.py.
# Uses: extract.py, stages_file.py, filing.py, capture_api.py.
import uuid
from datetime import datetime

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

from app.api import ui_models_graph as g
from app.pipeline import capture_api, filing
from app.pipeline.extract import UnreadableFile, kind_of, text_of
from app.pipeline.stages_file import DocumentRecord
from app.pipeline.stages_normalize import UNSAFE_FILENAME

# Config
CONNECTOR_ID = "conn_upload_console"
LARGEST_UPLOAD = 10 * 1024 * 1024  # 10 MB
UPLOAD_SENSITIVITIES = {"public", "internal", "confidential", "restricted"}


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
    receipt: dict | None = None  # step 10: what removing it cleared, once it was retired or erased
    version: int | None = None  # step 14: its place in a version chain
    replaced_by: str | None = None  # step 14: the newer version that replaced it, while that one is filed


class FilingRule(g.UiModel):
    id: str
    match: str
    cluster_id: str
    type: str
    sensitivity: str
    retention_days: int


def receipt_of(lane, document_id: str) -> dict | None:
    """The receipt of the finished removal of this document, if there is one."""
    done = [r for r in lane.records.list_kind("forget_request") if r["document_id"] == document_id and r["status"] == "done"]
    return done[-1]["receipt"] if done else None


def erased_view(lane, tombstone: dict) -> dict:
    """An erased document leaves a row with no content: no title, no file name, only the receipt."""
    return Document(
        id=tombstone["document_id"], tenant_id=lane.seed["tenant_id"], cluster_id=lane.seed["cluster_id"], title="Removed", source="Lisena upload",
        type="file", sensitivity="internal", extraction_status="erased", linked_facts=[], retention_days=0, filing_rule="uploads",
        uploaded_by=tombstone["erased_by"], uploaded_at=str(tombstone["erased_at"]), size_kb=0, personal_data=False, receipt=receipt_of(lane, tombstone["document_id"]),
    ).ui()


def document_view(lane, record: dict) -> dict:
    return Document(
        id=record["document_id"], tenant_id=lane.seed["tenant_id"], cluster_id=lane.seed["cluster_id"], title=record["title"], source="Lisena upload",
        type=record.get("doc_type") or record["kind"].lstrip(".") or "file", sensitivity=record["sensitivity"], extraction_status=record["status"],
        linked_facts=[], retention_days=record.get("retention_days", filing.FALLBACK_RULE["retention_days"]), filing_rule=record.get("filing_rule", "uploads"),
        uploaded_by=record["uploaded_by"], uploaded_at=str(record["uploaded_at"]), size_kb=max(1, record["size_bytes"] // 1024),
        personal_data=record["personal_data"], receipt=receipt_of(lane, record["document_id"]) if record["status"] == "retired" else None,
        version=record.get("version", 1), replaced_by=filing.replaced_by(lane.records, record),
    ).ui()


def documents_view(lane) -> list[dict]:
    """The Library: newest first."""
    shown = [document_view(lane, record) for record in lane.records.list_kind("document")]
    shown += [erased_view(lane, tombstone) for tombstone in lane.records.list_kind("tombstone")]
    return sorted(shown, key=lambda d: d["uploadedAt"], reverse=True)


def filing_rules_view(lane) -> list[dict]:
    """How new documents are filed, in the order the rules are tried."""
    return [FilingRule(id=rule["id"], match=rule["match"], cluster_id=lane.seed["cluster_id"], type=rule["type"] or "file kind", sensitivity=rule["sensitivity"],
                       retention_days=rule["retention_days"]).ui() for rule in filing.rules_of(lane.seed)]


def chunks_view(lane, document_id: str) -> list[dict]:
    """The text of a document as filed, one entry per chunk. Retired documents keep theirs; erased ones have none."""
    record = lane.records.load("document", document_id)
    if record is None:
        raise HTTPException(404, "not_found")
    prefix = f"{record['title']}: "
    return [{"id": body["item_id"], "text": body["text"].removeprefix(prefix)} for body in lane.chunks.of_document(document_id) if body["kind"] == "chunk"]


def accept(lane, persona: str, filename: str, data: bytes, sensitivity: str, evidence_for: dict | None = None) -> dict:
    """Store the original, record it as pending, and hand the text to S1. Raises HTTPException for a bad file.
    evidence_for (step 16) says which evidence request it answers, so extraction looks for that fact."""
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
                            size_bytes=len(data), uploaded_by=persona, uploaded_at=lane.now, sensitivity=sensitivity, status="pending", original_uri=original_uri,
                            evidence_for=evidence_for)
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
