# vault_routes.py: step 14, the librarian's answers from the console: Accept (the candidate becomes a verified fact on main),
# Reject, and, for a conflict, Propose (slice 4: a change request when the new claim wins). A steward (L2) or a leader (L1) may
# answer; Accept on a conflict is refused (409). Used by: routes.py (registers before the general ops route). Uses: fact_commit.py, fact_conflicts.py.
from fastapi import FastAPI, Header, HTTPException, Request

from app.api import fact_conflicts
from app.pipeline import fact_commit

# Config
MAY_SETTLE = {"L1", "L2"}  # decision 2 of the step 14 plan: a new fact is C2


def register(app: FastAPI, lane, check) -> None:
    """POST ops/librarianAccept, ops/librarianPropose and ops/librarianReject, with {itemId}. Must be added before the general ops route."""

    def settle(tenant: str, request_body: dict, persona: str, action) -> dict:
        check(tenant, persona)
        if lane.seed["people"][persona]["tier"] not in MAY_SETTLE:
            raise HTTPException(403, "not_a_steward")
        try:
            answer = action(lane, str(request_body.get("itemId", "")), persona)
            return answer if isinstance(answer, dict) else {"ok": True, "factId": answer}
        except LookupError:
            raise HTTPException(404, "not_found") from None
        except fact_commit.NotOpen as reason:
            raise HTTPException(409, str(reason)) from None

    @app.post("/api/t/{tenant}/ops/librarianAccept")
    async def accept(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        return settle(tenant, await request.json(), x_persona, fact_commit.accept)

    @app.post("/api/t/{tenant}/ops/librarianPropose")
    async def propose(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        return settle(tenant, await request.json(), x_persona, fact_conflicts.propose)

    @app.post("/api/t/{tenant}/ops/librarianReject")
    async def reject(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        return settle(tenant, await request.json(), x_persona, fact_commit.reject)
