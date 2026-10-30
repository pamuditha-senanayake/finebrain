# memory_fixes.py: from drift to a fix an L1 user decides (stage 6, Docs/CB_Living_Memory_Architecture.md section 8b).
# A new skill or policy drift drafts its change in Studio and opens it as a change request at C3 or higher, so an L1 user
# approves it; security drift has no draft and goes to the L1 leaders as an incident. The drift's state follows the change:
# sent to L1, waiting (the approval is out), approved (merged; the 14-day re-check starts), or back to detected with the
# reason when it is rejected. A drift whose fix cannot be drafted on its own is still sent to L1 to decide. Since stage 7 the
# page's two actions live here too: confirm a surprise as a normal way of working, and send a skill drafted from traces.
# Used by: routes.py (register), tests/test_memory_fixes.py, tests/test_memory_views.py. Uses: studio_review.py, studio_approvals.py, studio_state.py,
# studio_changes.py (notify), ready_notices.py (leaders), stages_memory_drift.py.
import re
from datetime import datetime
from types import SimpleNamespace

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel

from app.api import memory_views
from app.api.ready_notices import leaders
from app.api.studio_approvals import open_change
from app.api.studio_changes import ChangeRecord, notify
from app.api.studio_draft import StudioError
from app.api.studio_review import review
from app.api.studio_state import Studio
from app.pipeline import stages_memory as memory
from app.pipeline import stages_memory_drift
from app.pipeline import stages_memory_flow as flow
from app.pipeline.contracts_memory import AreaMatch, DriftFix, DriftFlag, DriftRecheck, SkillDraft
from app.pipeline.stages_learn import week_of, zone_of
from app.pipeline.stages_normalize import claim
from app.pipeline.contracts_run import ApprovalRequest, Decision
from app.pipeline.observe import count, log_event

# Config
DRAFTER = "Living memory"  # not a person, so an L1 user other than a drafter decides
L1_LEVEL = 3  # C3 and up are approved by an L1 user (studio_approvals.APPROVERS)
NEW_DAYS = re.compile(r"up to (\d+) days")
DRIFT_PAGE = "/l1/memory"
DRAFT_OF_CHANGE = "memory_draft_of_change"  # records kind keyed by change request id
MAY_ACT = {"L1", "L2"}  # stewards and leaders answer surprises and send drafts; an L1 user still approves each change
CLOSED = {"rejected": "L1 rejected the fix", "changes_requested": "L1 asked for changes to the fix", "conflict": "The fix met a newer change and could not merge"}


# --- Drafting the change

def flow_of(st: Studio, item_id: str) -> dict | None:
    """The workflow that holds this skill or policy, read from Studio."""
    return next((flow for flow in st.flows.values() if any(part["id"] == item_id for part in st.scope(flow))), None)


def change_for(st: Studio, flag: DriftFlag) -> dict | None:
    """The Studio change that would fix the drift, or None when it cannot be drafted without a person."""
    item, flow = st.items.get(flag.subject.id), flow_of(st, flag.subject.id)
    if not item or not flow or not flag.fix:
        return None
    if flag.kind == "policy":
        days = NEW_DAYS.search(flag.fix.summary)
        fields = {"param.days": int(days.group(1))} if days and "param.days" in item["fields"] else None
    else:
        fields = {"steps": [*item["fields"].get("steps", []), flag.fix.summary]}
    return {"intent": "update", "kind": flag.kind, "targetId": flag.subject.id, "workflowId": flow["id"], "patch": {"fields": fields}} if fields else None


def open_fix(lane, flag: DriftFlag) -> DriftFlag:
    """Draft, review, and open the change at L1 level; without a draft, ask the L1 leaders to decide."""
    st = Studio.of(lane)
    change = change_for(st, flag)
    try:
        proposal = review(lane, st.flows[change["workflowId"]]["dri"], change, st) if change else None
    except StudioError as refused:  # e.g. the drafted value is already in force; a person decides, the night goes on
        log_event("MEMORY", "fix_refused", flag_id=flag.flag_id, reason=str(refused))
        proposal = None
    if proposal is None:
        tell_leaders(lane, flag, "No fix could be drafted on its own. Please decide what should change.")
        return lane.drift.move(flag.model_copy(update={"state": "sent_to_l1"}), lane.now, "sent to L1 without a draft")
    proposal = {**proposal, "review": {**proposal["review"], "criticality": max(L1_LEVEL, proposal["review"]["criticality"])}}
    opened = open_change(lane, DRAFTER, change, proposal, f"From the living memory: {flag.summary}. Evidence: {', '.join(flag.evidence_trace_ids[:5])}")
    fix = DriftFix(summary=flag.fix.summary, change_request_id=opened["changeRequestId"])
    return lane.drift.move(flag.model_copy(update={"state": "sent_to_l1", "fix": fix}), lane.now, f"change request {fix.change_request_id}")


def tell_leaders(lane, flag: DriftFlag, ask: str) -> None:
    for person in leaders(lane):
        notify(lane, person, f"{flag.kind.capitalize()} drift: {flag.subject.name}", f"{flag.summary}. {ask}", DRIFT_PAGE, "approval")


# --- Following the drift and its change

def on_flag(lane, envelope) -> None:
    """A new drift: security goes to the L1 leaders as an incident; skill and policy drift get their fix drafted."""
    flag = lane.drift.get(DriftFlag.model_validate(envelope.payload).flag_id)
    if flag is None or flag.state != "detected" or (flag.fix and flag.fix.change_request_id):
        return  # a redelivery, or already on its way
    if flag.kind == "security":
        tell_leaders(lane, flag, "An action finished although its access check said deny.")
        lane.drift.move(flag.model_copy(update={"state": "sent_to_l1"}), lane.now, "incident sent to L1")
        return
    open_fix(lane, flag)
    count(f"memory.fix_opened.{flag.kind}")


def on_requested(lane, envelope) -> None:
    """The approval request for a drift's change went out: the L1 user has it waiting."""
    approval = ApprovalRequest.model_validate(envelope.payload)
    flag = lane.drift.by_change(approval.subject.ref) if approval.subject.kind == "change_request" else None
    if flag and flag.state == "sent_to_l1":
        lane.drift.move(flag.model_copy(update={"state": "awaiting_approval"}), lane.now, f"approval {approval.approval_id} with L1")


def follow(lane, flag: DriftFlag) -> DriftFlag:
    """Move the drift to where its change request now stands, read by its key. Safe to repeat: the night does it for any
    message that came before Studio had applied it."""
    stored = lane.records.load("change_request", flag.fix.change_request_id) if flag.fix and flag.fix.change_request_id else None
    status = ChangeRecord.model_validate(stored).status if stored else None
    if status == "awaiting_approval" and flag.state == "sent_to_l1":
        return lane.drift.move(flag.model_copy(update={"state": "awaiting_approval"}), lane.now, "waiting for L1")
    if status == "merged" and flag.state != "approved":
        recheck = DriftRecheck(until=stages_memory_drift.approved_until(lane), result="watching")
        return lane.drift.move(flag.model_copy(update={"state": "approved", "recheck": recheck}), lane.now, "approved and live")
    if status in CLOSED:
        note = CLOSED[status]
        return lane.drift.move(flag.model_copy(update={"state": "detected", "reopened_note": note, "fix": DriftFix(summary=flag.fix.summary, change_request_id=None)}), lane.now, note)
    return flag


def on_decided(lane, envelope) -> None:
    """After Studio has applied an L1 decision, the drift follows its change."""
    decision = Decision.model_validate(envelope.payload)
    approval = lane.records.load("approval", decision.approval_id)
    flag = lane.drift.by_change(approval["subject"]["ref"]) if approval and approval["subject"]["kind"] == "change_request" else None
    if flag and flag.state in ("sent_to_l1", "awaiting_approval"):
        follow(lane, flag)
    if approval and approval["subject"]["kind"] == "change_request":
        follow_drafts(lane, approval["subject"]["ref"])


def sync(lane) -> int:
    """The night's catch-up: a new drift whose message was missed is sent now, and a decision whose message arrived before
    Studio applied it is followed. A drift L1 sent back (it has a note) waits for its next raise instead. Returns drifts moved."""
    moved: set[str] = set()
    for flag in lane.drift.in_state("detected"):
        if not flag.reopened_note and not (flag.fix and flag.fix.change_request_id):
            on_flag(lane, SimpleNamespace(payload=flag.model_dump(mode="json")))
            if lane.drift.get(flag.flag_id).state != "detected":
                moved.add(flag.flag_id)
    for state in ("sent_to_l1", "awaiting_approval"):
        for flag in lane.drift.in_state(state):
            if flag.fix and flag.fix.change_request_id and follow(lane, flag).state != state:
                moved.add(flag.flag_id)
    log_event("memory", "drift_synced", moved=len(moved))
    return len(moved)


# --- What a person does on the page

class NotPossible(Exception):
    """The action does not apply to this item as it stands; the reason is a short code the page explains."""


class Answered(BaseModel):
    trace_id: str
    pattern_id: str
    by: str
    at: datetime


class DraftOfChange(BaseModel):
    """Which skill draft a change request carries, so a decision finds its draft by key (records kind DRAFT_OF_CHANGE)."""
    draft_id: str


def confirm_surprise(lane, trace_id: str, by: str) -> dict:
    """A person says a surprise is a normal way to work: it becomes a pattern in its area, counted, and leaves To review."""
    trace = lane.traces.get(trace_id)
    if trace is None:
        raise LookupError(trace_id)
    if lane.records.load(memory_views.CLOSED_KIND, trace_id):
        raise NotPossible("already_answered")
    if not claim(lane.memory_claims, f"confirm:{trace_id}"):  # two presses at once: one acts; a crash frees it when the claim expires
        raise NotPossible("already_answered")
    pattern = memory.confirm(trace, lane.patterns)
    if pattern is None:
        raise NotPossible("area_full")
    lane.patterns.count(pattern, week_of(trace.started_at, zone_of(lane)), trace_id)
    match = AreaMatch(trace_id=trace_id, tenant_id=trace.tenant_id, area=trace.area, pattern_id=pattern.pattern_id, pattern_key=pattern.key, similarity=1.0, match="normal")
    lane.records.save(flow.MATCH_KIND, trace_id, match)
    lane.records.save(memory_views.CLOSED_KIND, trace_id, Answered(trace_id=trace_id, pattern_id=pattern.pattern_id, by=by, at=lane.now))
    lane.audit.append(f"memory:{trace_id}:confirmed", "memory.confirmed", {"by": by, "at": lane.now.isoformat(), "reason": f"normal way of working in {trace.area}"})
    return {"patternId": pattern.pattern_id}


def send_draft(lane, draft_id: str, workflow_id: str, by: str) -> dict:
    """A skill drafted from traces goes to an L1 user as a new skill in the workflow a person chose."""
    stored = lane.records.load(stages_memory_drift.DRAFT_KIND, draft_id)
    st = Studio.of(lane)
    flow_ = st.flows.get(workflow_id)
    if stored is None or flow_ is None:
        raise LookupError(draft_id if stored is None else workflow_id)
    if stored["state"] != "draft":
        raise NotPossible("already_sent")
    if not claim(lane.memory_claims, f"send:{draft_id}"):
        raise NotPossible("already_sent")
    shown = memory_views.draft_view(lane, stored)
    change = {"intent": "create", "kind": "skill", "targetId": None, "workflowId": workflow_id,
              "patch": {"name": shown.name, "fields": {"trigger": f"Work in {memory_views.AREA_NAMES[stored['area']]} that starts like this", "steps": [s.title for s in shown.steps]}}}
    proposal = review(lane, flow_["dri"], change, st)
    proposal = {**proposal, "review": {**proposal["review"], "criticality": max(L1_LEVEL, proposal["review"]["criticality"])}}
    opened = open_change(lane, DRAFTER, change, proposal, f"Drafted from {stored['support']} traces by the living memory; sent by {by}")
    lane.records.save(DRAFT_OF_CHANGE, opened["changeRequestId"], DraftOfChange(draft_id=draft_id))
    lane.records.save(stages_memory_drift.DRAFT_KIND, draft_id, SkillDraft.model_validate({**stored, "state": "in_review", "change_request_id": opened["changeRequestId"]}))
    return {"changeRequestId": opened["changeRequestId"]}


def follow_drafts(lane, cr_id: str) -> None:
    """A skill draft follows its change request: approved when merged, rejected when L1 says no."""
    record, carried = lane.records.load("change_request", cr_id), lane.records.load(DRAFT_OF_CHANGE, cr_id)
    if not record or not carried or record["status"] not in ("merged", "rejected"):
        return
    stored = lane.records.load(stages_memory_drift.DRAFT_KIND, carried["draft_id"])
    lane.records.save(stages_memory_drift.DRAFT_KIND, stored["draft_id"], SkillDraft.model_validate({**stored, "state": "approved" if record["status"] == "merged" else "rejected"}))


async def body_of(request: Request) -> dict:
    try:
        return await request.json()
    except ValueError:
        return {}


def register(app, lane, check) -> None:
    """The consumers (after Studio's own consumer of approvals.decided, so the change request already shows the decision),
    and the page's two actions, before the general ops route."""
    if getattr(lane, "drift", None) is None:
        return
    lane.bus.subscribe("drift.flags", "memory_fixes", "S13", lambda envelope: on_flag(lane, envelope))
    lane.bus.subscribe("approvals.requested", "memory_fixes", "S8", lambda envelope: on_requested(lane, envelope))
    lane.bus.subscribe("approvals.decided", "memory_fixes", "S14", lambda envelope: on_decided(lane, envelope))

    def act(action, persona: str, *args) -> dict:
        if lane.seed["people"][persona]["tier"] not in MAY_ACT:
            raise HTTPException(403, "not_a_steward")
        try:
            return action(lane, *args, persona)
        except LookupError:
            raise HTTPException(404, "not_found") from None
        except NotPossible as reason:
            raise HTTPException(409, str(reason)) from None

    @app.post("/api/t/{tenant}/ops/memoryConfirm")
    async def confirm(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        return act(confirm_surprise, x_persona, str((await body_of(request)).get("traceId", "")))

    @app.post("/api/t/{tenant}/ops/memorySendDraft")
    async def send(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        body = await body_of(request)
        return act(send_draft, x_persona, str(body.get("draftId", "")), str(body.get("workflowId", "")))
