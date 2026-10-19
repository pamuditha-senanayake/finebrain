# grants.py: step 16 slice 5, data source grants (D04's third action). A request whose item a data source could supply can ask
# for read access to it. That is C4: two different L1 leaders approve, nobody approves their own request, and a cooling period
# follows (S8's rules) before the grant is active. Revoking ends it at once. Nothing is fetched under a grant yet: that needs the
# source's connector (open question 3), so the DRI still uploads. Used by: grant_views.py, routes.py (decide), hq.py (sweep), tests.
# Uses: stages_decide.py, stages_govern.py (cooling), stages_ready.py, studio_changes.py (notify), ready_notices.py (leaders).
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.api.ready_notices import leaders, tell
from app.pipeline import stages_decide, stages_ready
from app.pipeline.contracts_run import ApprovalRequest, ApprovalSubject, Approvers, Decision
from app.pipeline.stages_govern import C4_COOLING_HOURS

# Config
KIND, LEVEL, DUE_HOURS = "grant", 4, 72
APPROVERS = Approvers(tier="L1", count=2, roles=["leader"])  # C4: two different leaders


class Grant(BaseModel):
    grant_id: str
    request_id: str
    source: str
    scope: str
    retention_days: int
    agents: list[str]
    revoke: str
    status: str  # pending, approved (cooling), active, rejected, revoked
    requested_by: str
    approval_id: str
    created_at: datetime
    approved_by: list[str] = []
    cooling_until: datetime | None = None


class NotPossible(Exception):
    """The request has no grant to ask for, or one is already waiting or active."""


def save(lane, grant: Grant, **changes) -> Grant:
    grant = grant.model_copy(update=changes)
    lane.records.save(KIND, grant.grant_id, grant)
    return grant


def set_request(lane, request_id: str, status: str) -> None:
    stored = lane.records.load(stages_ready.REQUEST_KIND, request_id)
    stages_ready.update(lane, stored, {"status": status})


# --- Asking (D04)

def request_grant(lane, request_id: str, person: str) -> dict:
    """Open the C4 approval for the grant this request suggests, and pause the request while it waits."""
    stored = lane.records.load(stages_ready.REQUEST_KIND, request_id)
    if stored is None:
        raise LookupError(request_id)
    suggested = stored.get("suggested_grant")
    waiting = {g["source"] for g in lane.records.list_kind(KIND) if g["status"] in ("pending", "approved", "active")}
    if stored["status"] != "open" or not suggested or suggested["source"] in waiting:
        raise NotPossible("no_grant_to_ask_for")
    grant_id, due = lane.new_id("g"), lane.now + timedelta(hours=DUE_HOURS)
    approval = ApprovalRequest(approval_id=lane.new_id("apr"), subject=ApprovalSubject(kind="grant", ref=grant_id), criticality=LEVEL,
                               summary_plain=f"Grant read access to {suggested['source']}. {suggested['scope']}.", evidence_refs=[request_id],
                               required_approvers=APPROVERS, dri_id=stages_decide.find_person(APPROVERS, lane.seed["people"]), due_at=due, expires_at=due)
    grant = Grant(grant_id=grant_id, request_id=request_id, status="pending", requested_by=person, approval_id=approval.approval_id, created_at=lane.now, **suggested)
    lane.records.save(KIND, grant_id, grant)
    lane.records.save("approval", approval.approval_id, approval)
    lane.bus.publish("approvals.requested", "approval.requested", approval, "readiness")
    set_request(lane, request_id, "awaiting_grant_approval")
    tell(lane, leaders(lane), f"C4: grant access to {suggested['source']}", "Two L1 leaders must approve.")
    return {"ok": True, "grantId": grant_id, "approvalId": approval.approval_id}


# --- Deciding (S8's rules, C4)

def grant_of(lane, approval: dict | None) -> Grant | None:
    if not approval or approval["subject"]["kind"] != KIND:
        return None
    stored = lane.records.load(KIND, approval["subject"]["ref"])
    return Grant.model_validate(stored) if stored else None


def state_of(approval: dict, grant: Grant) -> stages_decide.ApprovalState:
    return stages_decide.ApprovalState(request=ApprovalRequest.model_validate(approval), assignee=approval["dri_id"], expires_after_seconds=0,
                                       approved_by=grant.approved_by)


def refusal_for(lane, approval: dict, decision: Decision) -> tuple[int, str] | None:
    """The console's check before a decision goes on the bus: the grant must be waiting, and the decider allowed."""
    grant = grant_of(lane, approval)
    if grant is None or grant.status != "pending":
        return 409, "approval_closed"
    reason = stages_decide.refusal(decision, state_of(approval, grant), lane.seed["people"], grant.requested_by)
    return (409, reason) if reason else None


def on_decision(lane, envelope) -> None:
    """approvals.decided for a grant: count the leaders; with two, cool down; a rejection gives the request back to the DRI."""
    decision = Decision.model_validate(envelope.payload)
    approval = lane.records.load("approval", decision.approval_id)
    grant = grant_of(lane, approval)
    if grant is None or refusal_for(lane, approval, decision):
        return
    if decision.decision == "reject":
        save(lane, grant, status="rejected")
        return set_request(lane, grant.request_id, "open")
    state = state_of(approval, grant)
    enough = decision.decision == "approve" and stages_decide.count_approvals(state, decision)
    seconds = C4_COOLING_HOURS * lane.seed.get("approval_timing", {}).get("seconds_per_cooling_hour", 3600)  # the same clock S8 uses
    save(lane, grant, approved_by=state.approved_by, **({"status": "approved", "cooling_until": lane.now + timedelta(seconds=seconds)} if enough else {}))


def sweep(lane) -> None:
    """Called by the HQ loop: an approved grant whose cooling has ended becomes active, and its request goes back to the DRI."""
    for stored in lane.records.list_kind(KIND):
        grant = Grant.model_validate(stored)
        if grant.status == "approved" and grant.cooling_until and grant.cooling_until <= lane.now:
            save(lane, grant, status="active")
            set_request(lane, grant.request_id, "open")  # nothing is fetched yet: the source's connector comes later
            lane.audit.append(f"grant:{grant.grant_id}:active", "grant.activated", {"by": "readiness", "at": lane.now.isoformat(), "reason": f"{grant.source}: {grant.scope}"})


def revoke(lane, grant_id: str, person: str) -> dict:
    stored = lane.records.load(KIND, grant_id)
    if stored is None:
        raise LookupError(grant_id)
    if stored["status"] != "active":
        raise NotPossible("not_active")
    save(lane, Grant.model_validate(stored), status="revoked")
    lane.audit.append(f"grant:{grant_id}:revoked", "grant.revoked", {"by": person, "at": lane.now.isoformat(), "reason": stored["source"]})
    return {"ok": True}
