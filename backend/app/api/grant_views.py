# grant_views.py: step 16 slice 5, grants on the console. GET grants (contracts/entity.ts Grant), a grant's approval in the shape
# To review shows (contracts/change.ts Approval), and the two ops: requestGrant (anyone the request concerns may ask) and
# revokeGrant (a steward or a leader). Used by: lists.py, versions_views.py (approval_of), routes.py (register), tests. Uses: grants.py.
from fastapi import FastAPI, Header, HTTPException, Request

from app.api import grants

# Config
SHOWN_STATUS = {"pending": "pending", "approved": "pending", "active": "active", "rejected": "revoked", "revoked": "revoked"}  # cooling still waits
APPROVAL_STATUS = {"pending": "pending", "approved": "approved", "active": "approved", "rejected": "rejected", "revoked": "approved"}
MAY_REVOKE = {"L1", "L2"}


def grants_view(lane) -> list[dict]:
    """Every grant, newest first. One still cooling shows as pending: nothing is readable yet."""
    stored = sorted(lane.records.list_kind(grants.KIND), key=lambda g: str(g["created_at"]), reverse=True)
    return [{"id": g["grant_id"], "tenantId": lane.seed["tenant_id"], "source": g["source"], "scope": g["scope"], "retentionDays": g["retention_days"],
             "agents": g["agents"], "revoke": g["revoke"], "status": SHOWN_STATUS[g["status"]], "requestedBy": g["requested_by"],
             "approvalId": g["approval_id"], "createdAt": str(g["created_at"])} for g in stored]


def approval_view(lane, approval: dict, grant: grants.Grant) -> dict:
    """A grant's approval, with every vote cast on it."""
    decisions = lane.records.history("decision", approval["approval_id"])
    person = lane.seed["people"].get(grant.requested_by, {})
    return {"id": approval["approval_id"], "tenantId": lane.seed["tenant_id"], "subject": {"kind": "grant", "id": grant.grant_id},
            "title": approval["summary_plain"].split(". ")[0], "summary": approval["summary_plain"], "criticality": approval["criticality"],
            "requiredApprovers": approval["required_approvers"], "dueAt": str(approval["due_at"]), "createdAt": grant.created_at.isoformat(),
            "votes": [{"by": d["decided_by"][0], "at": str(d["decided_at"]), "decision": d["decision"], "comment": d.get("comment", "")} for d in decisions
                      if d["decision"] in ("approve", "reject", "request_changes", "delegate")],
            "status": APPROVAL_STATUS[grant.status], "delegatedTo": None, "dri": approval["dri_id"],
            "drafter": {"kind": "human", "id": grant.requested_by, "name": person.get("name", grant.requested_by)},
            "evidence": approval["evidence_refs"], "correlationId": f"grant:{grant.grant_id}"}


def register(app: FastAPI, lane, check) -> None:
    """S8's consumer for grant decisions, and POST ops/requestGrant and ops/revokeGrant. Before the general ops route."""
    lane.bus.subscribe("approvals.decided", "grants", "S8", lambda envelope: grants.on_decision(lane, envelope))

    def answer(tenant: str, persona: str, action, *args) -> dict:
        check(tenant, persona)
        try:
            return action(lane, *args, persona)
        except LookupError:
            raise HTTPException(404, "not_found") from None
        except grants.NotPossible as reason:
            raise HTTPException(409, str(reason)) from None

    @app.post("/api/t/{tenant}/ops/requestGrant")
    async def request_grant(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        return answer(tenant, x_persona, grants.request_grant, str((await request.json()).get("requestId", "")))

    @app.post("/api/t/{tenant}/ops/revokeGrant")
    async def revoke(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        if lane.seed["people"][x_persona]["tier"] not in MAY_REVOKE:
            raise HTTPException(403, "not_a_steward")
        return answer(tenant, x_persona, grants.revoke, str((await request.json()).get("grantId", "")))
