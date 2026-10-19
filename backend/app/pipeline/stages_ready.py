# stages_ready.py: step 16 slice 2, S15 Readiness (D01 to D04). The check compares each obligation's required items with the
# verified facts (readiness_facts.py): every item not proven yet is a gap with its owner (the DRI). The first time a gap is seen
# it opens one evidence request, writes an audit entry and publishes K15 on evidence.gaps (the API tells the DRI). Requests follow
# the facts, escalate and expire (readiness_time.py). Safe to run again. Used by: api/ready_*.py, tests. Uses: readiness_*.py, contracts_graph.py, observe.py.
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.pipeline import readiness_facts, readiness_model, readiness_time
from app.pipeline.readiness_model import gap_id_of, request_id_of
from app.pipeline.readiness_time import ESCALATION_DAYS, escalation_level, when
from app.pipeline.contracts_graph import GapDetected, GapTarget
from app.pipeline.observe import count, log_event

# Config
REQUEST_KIND, CHECK_KIND = "evidence_request", "readiness_check"
STALE_AFTER = timedelta(hours=1)  # a screen that finds the last check older than this runs it again (the design's hourly tick)
CHECKER = "readiness"


class EvidenceRequest(BaseModel):
    """One request for one missing item, to the obligation's DRI."""
    request_id: str
    instance_id: str
    obligation_id: str
    evidence_key: str
    item: str  # in plain words, with the obligation it is for
    requested_from: str
    status: str  # open, fulfilled (a verified fact proves it now), expired (the due day passed without proof)
    due_at: datetime  # the day to prepare by
    created_at: datetime
    fulfilled_by: str | None = None  # the fact that proves it
    obligation_due_at: datetime | None = None  # slice 4: the due day it escalates towards
    escalation_level: int = 0  # slice 4: the last escalation step announced
    suggested_grant: dict | None = None  # slice 5: the data source that could supply it


class CheckRecord(BaseModel):
    at: datetime
    by: str
    gaps: int
    opened: int
    escalated: int = 0
    expired: int = 0


@dataclass
class CheckResult:
    """What one check changed, so the API can tell people."""
    opened: list[EvidenceRequest] = field(default_factory=list)
    escalated: list[tuple[dict, int]] = field(default_factory=list)  # (request, new step)
    expired: list[dict] = field(default_factory=list)


def update(lane, request: dict, changes: dict) -> None:
    lane.records.save(REQUEST_KIND, request["request_id"], EvidenceRequest.model_validate(request).model_copy(update=changes))


# --- Finding gaps (D02)

def gaps(lane, now: datetime) -> list[tuple[readiness_model.Instance, readiness_model.RequiredItem]]:
    """Every required item no verified fact proves yet, soonest due first."""
    found = []
    for instance in readiness_model.current(lane, now):
        proven, _, _ = readiness_facts.readiness_of(lane, instance, now)
        found += [(instance, item) for item, fact_id in proven if fact_id is None]
    return found


# --- Acting on them (D03, D04)

def action_of(lane, item: readiness_model.RequiredItem) -> str:
    """Ask the DRI; or, when a data source could supply it and no grant for it is active yet, ask for that grant."""
    active = {g["source"] for g in lane.records.list_kind("grant") if g["status"] == "active"}
    return "request_grant" if item.grant and item.grant["source"] not in active else "request_dri"


def open_request(lane, instance: readiness_model.Instance, item: readiness_model.RequiredItem, now: datetime) -> EvidenceRequest:
    """One request to the DRI, written to the audit log and announced as K15 for S3 and S8."""
    ob, gap_id = instance.obligation, gap_id_of(instance.instance_id, item.key)
    request = EvidenceRequest(request_id=request_id_of(instance.instance_id, item.key), instance_id=instance.instance_id, obligation_id=ob.id, evidence_key=item.key,
                              item=f"{item.label} for {ob.title}", requested_from=ob.dri, status="open", due_at=instance.prepare_by, created_at=now,
                              obligation_due_at=instance.due_at, escalation_level=escalation_level(instance.due_at, now),  # starts at the step it is already on
                              suggested_grant=item.grant)
    lane.records.save(REQUEST_KIND, request.request_id, request)
    lane.bus.publish("evidence.gaps", "gap.detected", GapDetected(
        gap_id=gap_id, target=GapTarget(kind="obligation", id=instance.instance_id), required_item=request.item, due_at=instance.due_at,
        prepare_by=instance.prepare_by, action=action_of(lane, item), dri_id=ob.dri, escalation_days=ESCALATION_DAYS, is_sample=True, detected_at=now), CHECKER)
    lane.audit.append(f"evidence:{request.request_id}", "evidence.requested", {"by": CHECKER, "at": now.isoformat(), "document_id": None,
                      "reason": f"Asked {ob.dri} for {request.item} before {instance.prepare_by.date().isoformat()} (sample)"})
    return request


def target_of(lane, request: dict, now: datetime) -> tuple[readiness_model.Instance, readiness_model.RequiredItem] | tuple[None, None]:
    """The obligation instance and required item a request asks for, while that instance is current."""
    instance = next((i for i in readiness_model.current(lane, now) if i.instance_id == request["instance_id"]), None)
    item = next((i for i in instance.obligation.items if i.key == request["evidence_key"]), None) if instance else None
    return (instance, item) if item else (None, None)


def follow_facts(lane, now: datetime) -> None:
    """Requests follow the facts: proven now means fulfilled by that fact; proof retired or erased means open again (D07)."""
    for stored in lane.records.list_kind(REQUEST_KIND):
        instance, item = target_of(lane, stored, now)
        fact_id = readiness_facts.proven_by(lane, instance, item, now) if item else None
        if stored["status"] == "open" and fact_id or stored["status"] == "fulfilled" and item and not fact_id:
            status = "fulfilled" if fact_id else "open"
            update(lane, stored, {"status": status, "fulfilled_by": fact_id})
            lane.audit.append(f"evidence:{stored['request_id']}:{status}:{now.isoformat()}", f"evidence.{status}", {"by": CHECKER, "at": now.isoformat(), "reason": stored["item"]})


def settle_dates(lane, now: datetime) -> None:
    """Requests from before slice 4 learn their obligation's due day, and one expired before that day opens again (an expiry
    is only true after the due day)."""
    for stored in lane.records.list_kind(REQUEST_KIND):
        instance, _ = target_of(lane, stored, now)
        if instance is None:
            continue
        item = next(i for i in instance.obligation.items if i.key == stored["evidence_key"])
        if not stored.get("obligation_due_at") or item.grant and not stored.get("suggested_grant"):  # requests from before slices 4 and 5
            update(lane, stored, {"obligation_due_at": instance.due_at, "suggested_grant": item.grant})
            stored = lane.records.load(REQUEST_KIND, stored["request_id"])
        if stored["status"] == "expired" and now <= instance.due_at:
            update(lane, stored, {"status": "open"})
            readiness_time.audit(lane, stored, "reopened", now, "expired before its due day")


def check(lane, now: datetime, by: str = CHECKER) -> CheckResult:
    """S15: requests follow the facts, late ones expire, the rest escalate, and each gap seen for the first time gets a request."""
    # Step 1: bring existing requests up to date
    settle_dates(lane, now)
    follow_facts(lane, now)
    result = CheckResult(expired=readiness_time.expire(lane, now, lambda r, c: update(lane, r, c)))
    result.escalated = readiness_time.escalate(lane, now, lambda r, c: update(lane, r, c))

    # Step 2: a request for every new gap
    found = gaps(lane, now)
    result.opened = [open_request(lane, instance, item, now) for instance, item in found
                     if lane.records.load(REQUEST_KIND, request_id_of(instance.instance_id, item.key)) is None]
    lane.records.save(CHECK_KIND, "latest", CheckRecord(at=now, by=by, gaps=len(found), opened=len(result.opened), escalated=len(result.escalated), expired=len(result.expired)))
    count("s15.gaps", len(found))
    log_event("S15", "checked", gaps=len(found), opened=len(result.opened), escalated=len(result.escalated), expired=len(result.expired), by=by)
    return result


def is_stale(lane, now: datetime) -> bool:
    """True when the check has not run for an hour: the screens then run it, so readiness is never older than that."""
    last = lane.records.load(CHECK_KIND, "latest")
    return last is None or now - when(last["at"]) > STALE_AFTER
