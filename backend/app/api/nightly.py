# nightly.py: S13's nightly review (step 15), at 02:00 on Temporal or on "Run overnight review now". It looks at the last
# 24 hours: failures by type, runs marked wrong grouped by Claude Opus with one fix drafted per group by Skillify (a C0 or
# C1 fix is applied at once, anything else waits for the DRI), the spike check, and what waits on approval. It writes the
# morning digest (contracts/ops.ts Digest) and tells the L1 leaders. Used by: learn_routes.py, lists.py (GET digest), hq.py
# (the schedule), tests/test_nightly.py. Uses: nightly_groups.py, skillify.py, run_marks.py, trend_views.py, versions_views.py, ready_notices.py.
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.api import nightly_groups, run_marks, skillify
from app.api.ready_notices import leaders
from app.api.studio_changes import notify
from app.api.trend_views import tell_owner
from app.api.versions_views import approval_of
from app.pipeline import stages_spike

# Config
WINDOW = timedelta(hours=24)
REVIEWER = "Nightly review"
DIGEST_KIND = "digest"
FAILED = ("failed", "escalated", "blocked", "abandoned")  # outcomes that count as failures, by name
MORNING_UNTIL = 6  # a review before 06:00 local time reports on the day before


class DigestRecord(BaseModel):
    """The morning digest, kept in the console's own shape (contracts/ops.ts Digest)."""
    date: str
    generatedAt: str
    generatedBy: str
    runs: int
    failures: int
    failureClasses: list[dict]
    items: list[dict]


# --- Helpers

def moment(text) -> datetime:
    """A stored time. Postgres gives times back ending in Z, which Python 3.10 cannot read."""
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def started(run: dict) -> datetime | None:
    return moment(run["steps"][0]["started_at"]) if run.get("steps") else None


def item(lane, kind: str, title: str, detail: str, criticality: int, href: str | None) -> dict:
    return {"id": lane.new_id("dg"), "kind": kind, "title": title, "detail": detail, "criticality": criticality, "href": href, "at": lane.now.isoformat()}


def failure_classes(runs: list[dict], marks: list[dict]) -> list[dict]:
    counted = {name: sum(run["outcome"] == name for run in runs) for name in FAILED}
    counted["marked wrong"] = len(marks)
    return [{"name": name, "count": count} for name, count in counted.items() if count]


def fix_items(lane, drafter, grouper, marks: list[dict]) -> list[dict]:
    """One fix per group of runs that went wrong the same way. A group Claude cannot fix stays in the failures."""
    runs = {mark["run_id"]: lane.records.load("run", mark["run_id"]) for mark in marks}
    shown = []
    for group in nightly_groups.group(grouper, marks, runs) if drafter else []:
        try:
            fixed = skillify.draft_fix(lane, drafter, group["run_ids"][0], REVIEWER, tuple(group["run_ids"][1:]), apply_low=True)
        except skillify.NotPossible:
            continue
        applied = fixed["revisionId"] is not None
        shown.append(item(lane, "auto_fix" if applied else "drafted", fixed["title"], f"{group['title']}. {fixed['why']}", fixed["criticality"],
                          f"/studio?wf={fixed['workflowId']}" if applied else f"/l1/approvals/{fixed['approvalId']}"))
    return shown


def trend_items(lane) -> list[dict]:
    """The spike check over every series; each new unusual week tells its owner and shows in the digest."""
    found = stages_spike.check(lane, lane.now)
    for trend in found:
        tell_owner(lane, trend)
    return [item(lane, "waiting", f"Unusual week: {t.metric}", f"{t.segment}: {t.latest} this week, {t.ratio}x usual.", 1, "/l1/trends") for t in found]


def waiting_items(lane) -> list[dict]:
    pending = [shown for shown in (approval_of(lane, a) for a in lane.records.list_kind("approval")) if shown["status"] == "pending"]
    return [item(lane, "waiting", a["title"], a["summary"], a["criticality"], f"/l1/approvals/{a['id']}") for a in pending]


def date_of(lane) -> str:
    local = lane.now.astimezone(ZoneInfo(lane.seed.get("timezone", "UTC")))
    return (local.date() - timedelta(days=1) if local.hour < MORNING_UNTIL else local.date()).isoformat()


# --- The review

def review(lane, drafter, grouper, by: str) -> dict:
    """Review the last 24 hours and write the morning digest. Returns it in the console's shape."""
    # Step 1: what happened: runs started in the window, and runs marked wrong in it that have no fix yet
    since = lane.now - WINDOW
    runs = [run for run in lane.records.list_kind("run") if (at := started(run)) and since < at <= lane.now]
    marks = [m for m in lane.records.list_kind(run_marks.MARK_KIND) if since < moment(m["at"]) <= lane.now and not skillify.fix_of(lane, m["run_id"])]

    # Step 2: fixes for what went wrong, the spike check, and what waits on a person
    items = fix_items(lane, drafter, grouper, marks) + trend_items(lane) + waiting_items(lane)
    classes = failure_classes(runs, marks)
    digest = {"date": date_of(lane), "generatedAt": lane.now.isoformat(), "generatedBy": REVIEWER, "runs": len(runs),
              "failures": sum(c["count"] for c in classes), "failureClasses": classes, "items": items}

    # Step 3: keep it, tell the leaders, audit it
    lane.records.save(DIGEST_KIND, digest["date"], DigestRecord(**digest))  # a second review the same day is a new version
    for leader in leaders(lane):
        notify(lane, leader, "Morning digest", f"{len(runs)} runs, {digest['failures']} failures, {sum(i['kind'] == 'auto_fix' for i in items)} fixed, "
               f"{sum(i['kind'] == 'drafted' for i in items)} drafted.", "/l1/digest", "digest")
    lane.audit.append(f"nightly:{lane.now.isoformat()}", "nightly.reviewed", {"by": by, "at": lane.now.isoformat(), "reason": f"digest for {digest['date']}"})
    return digest


def digest_view(lane) -> dict | None:
    """The latest digest, or None before the first review."""
    kept = lane.records.list_kind(DIGEST_KIND)
    return max(kept, key=lambda digest: digest["generatedAt"]) if kept else None
