# readiness_time.py: step 16 slice 4, S15 over time (D05). An open evidence request escalates as its obligation's due day nears
# (21, 14, 7 and 2 days before, sample values), once per step; past the due day it expires. Each change is written to the audit
# log and returned, so the API can tell the DRI (and, from step 3, the leaders). Used by: stages_ready.py (check), api/ready_views.py,
# tests. Uses: nothing local but the record shapes stages_ready.py saves.
from datetime import datetime

# Config
ESCALATION_DAYS = [21, 14, 7, 2]  # sample values: days before the due day when an unanswered request escalates
LEADERS_FROM = 3  # from this step on, the leaders hear about it too
CHECKER = "readiness"


def when(stored) -> datetime:
    """A saved time: records keep it with a trailing Z, which Python 3.10 cannot read."""
    return datetime.fromisoformat(str(stored).replace("Z", "+00:00"))


def deadline_of(request: dict) -> datetime:
    """The obligation's due day; requests from before slice 4 only kept their prepare-by day."""
    return when(request.get("obligation_due_at") or request["due_at"])


def escalation_level(deadline: datetime, now: datetime) -> int:
    """How many escalation days have passed: 0 three weeks out, 4 two days before the due day."""
    days_left = (deadline - now).days
    return sum(days_left <= day for day in ESCALATION_DAYS)


def audit(lane, request: dict, event: str, now: datetime, reason: str) -> None:
    lane.audit.append(f"evidence:{request['request_id']}:{event}:{now.isoformat()}", f"evidence.{event}",
                      {"by": CHECKER, "at": now.isoformat(), "reason": f"{request['item']}: {reason}"})


def escalate(lane, now: datetime, save) -> list[tuple[dict, int]]:
    """Raise each open request to the step it has reached, once. Returns (request, new level) for each one raised."""
    raised = []
    for request in lane.records.list_kind("evidence_request"):
        level = escalation_level(deadline_of(request), now)
        if request["status"] == "open" and level > request.get("escalation_level", 0):
            save(request, {"escalation_level": level})
            audit(lane, request, "escalated", now, f"step {level} of {len(ESCALATION_DAYS)}")
            raised.append((request, level))
    return raised


def expire(lane, now: datetime, save) -> list[dict]:
    """An open request whose due day has passed expires: the filing went without its proof. Returns those expired."""
    late = [r for r in lane.records.list_kind("evidence_request") if r["status"] == "open" and now > deadline_of(r)]
    for request in late:
        save(request, {"status": "expired"})
        audit(lane, request, "expired", now, "the due day passed without proof")
    return late
