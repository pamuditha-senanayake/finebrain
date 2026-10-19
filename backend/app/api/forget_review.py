# forget_review.py: step 10.3, review first. A request to remove a document shows what depends on it and the level,
# then waits for the L1 to confirm: once to retire, twice to erase (with a last warning between). Only then does
# pipeline/forget.py run. The server sets the level and counts the confirmations; the browser never does.
# Used by: forget_routes.py, documents.py. Uses: forget.py, forget_layers.py, forget_layers_data.py.
import json
from datetime import datetime

from pydantic import BaseModel

from app.api import forget_layers, forget_layers_data  # noqa: F401  (importing registers the layers)
from app.pipeline import forget

# Config
KIND = "forget_request"
LEVELS = {"retire": 3, "erase": 4}
CONFIRMATIONS = {"retire": 1, "erase": 2}
WARNINGS = {
    "retire": ["It stops showing in answers. Past answers stay."],
    "erase": ["This removes it everywhere. It cannot be undone.", "Last check. Erase it for good?"],
}
DEPENDENT_TYPES = ("policy", "skill", "knowledge")


class ForgetRequest(BaseModel):
    request_id: str
    document_id: str
    mode: str
    reason: str
    level: int
    requested_by: str
    created_at: datetime
    confirmations: int = 0
    status: str = "review"  # review, done, incomplete
    dependents: list[dict] = []
    receipt: dict | None = None


class NotAllowed(Exception):
    """The request cannot go on: `code` is the API error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def dependents_of(lane, item: forget.ForgetItem) -> list[dict]:
    """Policies, skills and other knowledge whose text names this document or one of its chunks."""
    marks = [item.document_id, *item.chunk_ids]
    own = set(item.chunk_ids)
    found = []
    for node_type in DEPENDENT_TYPES:
        for node in lane.graph.latest(node_type):
            node_id = node["_ref"]["id"]
            if node_id not in own and any(mark in json.dumps(node, default=str) for mark in marks):
                found.append({"type": node_type, "id": node_id, "label": node.get("name") or node.get("title") or node_id})
    return found


def view(request: ForgetRequest) -> dict:
    """What the console shows: the warning for the next confirmation, and how many are left."""
    left = max(CONFIRMATIONS[request.mode] - request.confirmations, 0) if request.status == "review" else 0
    warning = WARNINGS[request.mode][min(request.confirmations, len(WARNINGS[request.mode]) - 1)] if left else ""
    return {"requestId": request.request_id, "documentId": request.document_id, "mode": request.mode, "level": request.level, "status": request.status,
            "dependents": request.dependents, "confirmationsLeft": left, "warning": warning, "receipt": request.receipt}


def require_l1(lane, persona: str) -> None:
    if lane.seed["people"].get(persona, {}).get("tier") != "L1":
        raise NotAllowed("l1_only")


def open_request(lane, persona: str, document_id: str, mode: str, reason: str) -> dict:
    """Step 1: look at what depends on the document. Nothing is removed."""
    require_l1(lane, persona)
    if mode not in forget.MODES:
        raise NotAllowed("unknown_mode")
    try:
        item = forget.item_of(lane, document_id)
    except KeyError:
        raise NotAllowed("not_found") from None
    if item.record["status"] == "pending":
        raise NotAllowed("not_filed_yet")
    if mode == "retire" and item.record["status"] == "retired":
        raise NotAllowed("already_retired")
    request = ForgetRequest(request_id=lane.new_id("fgt"), document_id=document_id, mode=mode, reason=reason.strip()[:300], level=LEVELS[mode],
                            requested_by=persona, created_at=lane.now, dependents=dependents_of(lane, item))
    lane.records.save(KIND, request.request_id, request)
    return view(request)


def confirm(lane, persona: str, request_id: str) -> dict:
    """Steps 2 and 3: one confirmation more. The last one runs the job. A job that came back incomplete can be confirmed again."""
    require_l1(lane, persona)
    stored = lane.records.load(KIND, request_id)
    if stored is None:
        raise NotAllowed("not_found")
    request = ForgetRequest.model_validate(stored)
    if request.status == "done":
        raise NotAllowed("already_done")
    request = request.model_copy(update={"confirmations": min(request.confirmations + 1, CONFIRMATIONS[request.mode])})
    if request.confirmations >= CONFIRMATIONS[request.mode]:
        receipt = forget.run(lane, request.document_id, request.mode, persona, request.reason)
        request = request.model_copy(update={"receipt": receipt, "status": "done" if receipt["verified"] else "incomplete"})
    lane.records.save(KIND, request_id, request)
    return view(request)
