# studio_checks.py: what an approver sees before a Studio change goes live. The Edit Review Agent's findings become the
# test suite: one check per item the change touches, failing when the review found a break there. The impact note says
# plainly that no past runs were replayed, because Studio cannot replay runs yet; it never claims a replay that did not happen.
# Used by: studio_approvals.py (open_change), versions_views.py (older change requests). Uses: nothing local.
from datetime import datetime

# Config
SUITE = "Edit Review checks"
RISK = {"minimal": "low", "moderate": "medium", "breaking": "high"}


def broken_ids(review: dict, target_id: str) -> set[str]:
    """Items the review found a break on. A break with no reference is about the changed item itself."""
    return {(f["ref"] or {}).get("id") or target_id for f in review["findings"] if f["severity"] == "break"}


def tests_of(review: dict, ran_at: datetime) -> dict:
    """One check per affected item: it passes when the review found nothing that breaks it."""
    affected = review.get("affected") or []
    ids = [a["id"] for a in affected] or ["target"]
    broken = broken_ids(review, ids[0])
    failed = sum(item_id in broken for item_id in ids)
    if broken - set(ids):  # a break on something outside the affected list still fails the suite
        failed, ids = failed + 1, [*ids, "elsewhere"]
    total = len(ids)
    return {"suite": SUITE, "total": total, "passed": total - failed, "failed": failed, "passK": (total - failed) / total, "k": 1, "ranAt": ran_at.isoformat()}


def impact_of(review: dict) -> dict:
    """An honest impact note: what the review covered, and that no runs were replayed."""
    items, others = len(review.get("affected") or []), len(review.get("otherWorkflows") or [])
    reach = f"The Edit Review checked {items} item{'s' if items != 1 else ''}" + (f" and {others} other workflow{'s' if others != 1 else ''} sharing them." if others else ".")
    return {"runsReplayed": 0, "decisionsChanged": 0, "predictedRisk": RISK.get(review["verdict"], "medium"), "examples": [],
            "summary": f"No runs replayed: Studio cannot replay past runs yet. {reach}"}


def checks(review: dict, ran_at: datetime) -> tuple[dict, dict]:
    return tests_of(review, ran_at), impact_of(review)
