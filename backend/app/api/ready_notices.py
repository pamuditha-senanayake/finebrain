# ready_notices.py: step 16, who hears what when S15's check runs. The DRI is told of each new request, each escalation step and
# each expiry; from step 3, and on expiry, the leaders are told too. The check runs from "Check now", from the hourly Temporal
# schedule, and on a screen read when it is over an hour old. Used by: ready_views.py, ready_routes.py, hq.py (schedule), tests.
# Uses: stages_ready.py, readiness_time.py, studio_changes.py (notify).
from app.api.studio_changes import notify
from app.pipeline import readiness_time, stages_ready

# Config
EVIDENCE_PAGE = "/l1/digest?tab=evidence"


def leaders(lane) -> list[str]:
    return [pid for pid, person in lane.seed["people"].items() if person["tier"] == "L1" and "leader" in person["roles"]]


def tell(lane, people: list[str], title: str, body: str) -> None:
    for person in dict.fromkeys(people):  # a DRI who is also a leader hears it once
        notify(lane, person, title, body, EVIDENCE_PAGE, "evidence")


def run_check(lane, by: str) -> dict:
    """S15's check now, and the notices it calls for. Returns the counts the console's Check now shows."""
    result = stages_ready.check(lane, lane.now, by)
    for request in result.opened:
        tell(lane, [request.requested_from], f"Evidence needed: {request.item}", f"Please add it by {request.due_at.date().isoformat()} (sample).")
    for request, level in result.escalated:
        louder = leaders(lane) if level >= readiness_time.LEADERS_FROM else []
        days = (readiness_time.deadline_of(request) - lane.now).days
        tell(lane, [request["requested_from"], *louder], f"Still needed: {request['item']}", f"Due in {days} days (step {level} of {len(readiness_time.ESCALATION_DAYS)}).")
    for request in result.expired:
        tell(lane, [request["requested_from"], *leaders(lane)], f"Missed: {request['item']}", "The due day passed without proof (sample).")
    return {"gaps": len(stages_ready.gaps(lane, lane.now)), "requestsCreated": len(result.opened), "escalated": len(result.escalated), "expired": len(result.expired)}


def fresh(lane) -> None:
    """The hourly check when it is due; requests follow the facts on every read, so an accepted or retired proof shows at once."""
    if stages_ready.is_stale(lane, lane.now):
        run_check(lane, stages_ready.CHECKER)
    stages_ready.follow_facts(lane, lane.now)
