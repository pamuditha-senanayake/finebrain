# trend_views.py: unusual weeks on the console (step 15). GET trends in the console's TrendCard shape
# (contracts/trends.ts), and the notice that tells a trend's owner. Used by: lists.py, learn_routes.py, tests/test_spike.py.
# Uses: stages_spike.py, studio_changes.py (notify).
from app.api.studio_changes import notify
from app.pipeline import stages_spike

# Config
TRENDS_PAGE = "/l1/trends"


def trends_view(lane) -> list[dict]:
    """Every unusual week, newest first. The screen shows the new ones, one card at a time."""
    stored = sorted(lane.records.list_kind(stages_spike.TREND_KIND), key=lambda t: str(t["found_at"]), reverse=True)
    return [{"id": t["trend_id"], "tenantId": lane.seed["tenant_id"], "metric": t["metric"], "segment": t["segment"], "ownerId": t["owner_id"],
             "weeks": t["weeks"], "usual": t["usual"], "latest": t["latest"], "ratio": t["ratio"], "status": t["status"],
             "caseIds": t["case_ids"], "foundAt": str(t["found_at"])} for t in stored]


def tell_owner(lane, trend: stages_spike.TrendRecord) -> None:
    notify(lane, trend.owner_id, f"Unusual week: {trend.metric}", f"{trend.segment}: {trend.latest} this week, {trend.ratio}x the usual {trend.usual:g}.", TRENDS_PAGE)
