# stages_spike.py: S13's spike check (step 15). A week is unusual when its count is at least 3 times the usual week (the
# median of the 12 weeks before it) and at least 5, so a quiet series going from 1 to 3 stays quiet. Each unusual week is
# one trend record with an owner; it keeps up with the week's count, and Mark as known quiets it.
# Used by: api/learn_routes.py, api/trend_views.py, tests/test_spike.py. Uses: stages_learn.py (weeks, names).
import hashlib
from datetime import date, datetime, timedelta
from statistics import median
from typing import Literal

from pydantic import BaseModel

from app.pipeline import stages_learn

# Config
SPIKE_RATIO = 3.0
SPIKE_MIN = 5
HISTORY_WEEKS = 12
TREND_KIND = "trend"
CHECKER = "S13"


class TrendRecord(BaseModel):
    trend_id: str
    metric: str
    segment: str
    week: date
    owner_id: str
    weeks: list[int]  # the 11 weeks before, then this week: what the card draws
    usual: float
    latest: int
    ratio: float
    case_ids: list[str]
    status: Literal["new", "known"] = "new"
    found_at: datetime
    known_by: str | None = None
    known_at: datetime | None = None


class NotPossible(Exception):
    """The trend cannot change this way."""


# --- Helpers

def trend_id_of(metric: str, segment: str, week: date) -> str:
    return "tr_" + hashlib.sha1(f"{metric}|{segment}|{week}".encode()).hexdigest()[:12]


def history_of(counts: dict[date, int], week: date) -> list[int]:
    """The 12 weeks before this one, oldest first. A week with nothing recorded counted 0."""
    return [counts.get(week - timedelta(weeks=back), 0) for back in range(HISTORY_WEEKS, 0, -1)]


def owner_of(lane, metric: str, segment: str) -> str:
    """The DRI of the agent behind the series: the agent named, or the one the named skill runs on. Else the first L1 leader."""
    label = segment.rsplit(", ", 1)[0]
    agents = lane.seed.get("agents", {})
    skill_ids = [skill["id"] for skill in lane.seed.get("skills", []) if skill.get("name") == label]
    runs_skill = [rule["agent_id"] for rule in lane.seed.get("resolver_rules", []) if rule.get("skill_id") in skill_ids]
    named = [agent_id for agent_id in agents if stages_learn.agent_name(lane, agent_id) == label]
    for agent_id in (named if metric == "Escalations" else runs_skill):
        if dri := (agents[agent_id].get("studio") or {}).get("dri"):
            return dri
    return next(pid for pid, person in lane.seed["people"].items() if person["tier"] == "L1")


def measure(lane, metric: str, segment: str, week: date) -> dict | None:
    """The week's numbers when it is unusual, else None."""
    counts = lane.counts.weeks(metric, segment)
    history, latest = history_of(counts, week), counts.get(week, 0)
    usual = float(median(history))
    ratio = latest / max(usual, 1.0)  # a series that is usually 0 still needs SPIKE_MIN to be unusual
    if latest < SPIKE_MIN or ratio < SPIKE_RATIO:
        return None
    return {"weeks": history[1:] + [latest], "usual": usual, "latest": latest, "ratio": round(ratio, 1), "case_ids": lane.counts.cases_of(metric, segment, week)}


def audit(lane, trend: TrendRecord, event: str, by: str, now: datetime) -> None:
    lane.audit.append(f"trend:{trend.trend_id}:{event}:{now.isoformat()}", f"trend.{event}",
                      {"by": by, "at": now.isoformat(), "reason": f"{trend.metric}, {trend.segment}: {trend.latest} in the week of {trend.week} ({trend.ratio}x usual)"})


# --- The check

def check_series(lane, metric: str, segment: str, now: datetime) -> TrendRecord | None:
    """Check this week of one series. Returns the trend only when it is newly found; a known one just keeps its numbers current."""
    week = stages_learn.week_of(now, stages_learn.zone_of(lane))
    numbers = measure(lane, metric, segment, week)
    if numbers is None:
        return None
    trend_id = trend_id_of(metric, segment, week)
    if stored := lane.records.load(TREND_KIND, trend_id):
        if stored["latest"] != numbers["latest"]:
            lane.records.save(TREND_KIND, trend_id, TrendRecord.model_validate(stored).model_copy(update=numbers))
        return None
    trend = TrendRecord(trend_id=trend_id, metric=metric, segment=segment, week=week, owner_id=owner_of(lane, metric, segment), found_at=now, **numbers)
    lane.records.save(TREND_KIND, trend_id, trend)
    audit(lane, trend, "found", CHECKER, now)
    return trend


def check(lane, now: datetime) -> list[TrendRecord]:
    """Check this week of every series. Returns the trends newly found."""
    found = [check_series(lane, metric, segment, now) for metric, segment in lane.counts.series()]
    return [trend for trend in found if trend]


def mark_known(lane, trend_id: str, by: str, now: datetime) -> TrendRecord:
    """Quiet one unusual week: it leaves the Trends screen and is not raised again."""
    stored = lane.records.load(TREND_KIND, trend_id)
    if stored is None:
        raise LookupError(trend_id)
    if stored["status"] == "known":
        raise NotPossible("already_known")
    trend = TrendRecord.model_validate(stored).model_copy(update={"status": "known", "known_by": by, "known_at": now})
    lane.records.save(TREND_KIND, trend_id, trend)
    audit(lane, trend, "marked_known", by, now)
    return trend
