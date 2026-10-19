# forget_routes.py: step 10, the two calls for removing a document. Used by: routes.py. Uses: forget_review.py.
from fastapi import FastAPI, Header, HTTPException

from app.api import forget_review

# Config
STATUS = {"l1_only": 403, "not_found": 404, "unknown_mode": 400, "not_filed_yet": 409, "already_retired": 409, "already_done": 409}


def register(app: FastAPI, lane, check) -> None:
    """Must be added before the catch-all POST route."""

    def answer(action) -> dict:
        try:
            return action()
        except forget_review.NotAllowed as error:
            raise HTTPException(STATUS[error.code], error.code) from None

    @app.post("/api/t/{tenant}/documents/{document_id}/forget")
    def start(tenant: str, document_id: str, body: dict, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        return answer(lambda: forget_review.open_request(lane, x_persona, document_id, str(body.get("mode", "")), str(body.get("reason", ""))))

    @app.post("/api/t/{tenant}/forget/{request_id}/confirm")
    def confirm(tenant: str, request_id: str, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        return answer(lambda: forget_review.confirm(lane, x_persona, request_id))
