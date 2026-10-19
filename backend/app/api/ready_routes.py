# ready_routes.py: step 16, readiness from the console. "Check now" runs S15's check at once (the screens also run it when it is
# over an hour old); a steward (L2) or a leader (L1) may run it. Uploading to an evidence request files the document with what it
# was asked for, so extraction looks for that fact; a person still accepts it in the Vault before the gap closes.
# Used by: routes.py (registers before the general ops route). Uses: ready_views.py, documents.py, stages_ready.py.
from fastapi import FastAPI, File, Header, HTTPException, UploadFile

from app.api import documents, ready_views
from app.pipeline import stages_ready

# Config
MAY_CHECK = {"L1", "L2"}


def register(app: FastAPI, lane, check) -> None:
    """POST ops/runReadinessScheduler (the console's name for Check now) and evidence-requests/{id}/upload. Before the catch-all routes."""

    @app.post("/api/t/{tenant}/ops/runReadinessScheduler")
    def run_now(tenant: str, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        if lane.seed["people"][x_persona]["tier"] not in MAY_CHECK:
            raise HTTPException(403, "not_a_steward")
        return ready_views.run_check(lane, x_persona)

    @app.post("/api/t/{tenant}/evidence-requests/{request_id}/upload", status_code=202)
    async def upload(tenant: str, request_id: str, file: UploadFile = File(...), x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        stored = lane.records.load(stages_ready.REQUEST_KIND, request_id)
        if stored is None:
            raise HTTPException(404, "not_found")
        instance, item = stages_ready.target_of(lane, stored, lane.now)
        if stored["status"] != "open" or item is None:
            raise HTTPException(409, "request_not_open")
        asked = {"request_id": request_id, "label": stored["item"], "predicate": item.predicate, "period": instance.period}
        return documents.accept(lane, x_persona, file.filename or "evidence.txt", await file.read(), "confidential", evidence_for=asked)
