# readiness_model.py: step 16, S15's obligations. A tenant's obligations are templates (samples/hq_obligations.json); each one
# falls due on a day each month, a day each year, or when a verified fact says a contract's term ends. The current instance is
# the next one due, with the period it covers (for monthly ones, the month before) and the day to prepare by.
# Used by: readiness_facts.py, api/ready_views.py, tests/test_ready.py. Uses: entity_match.py.
import calendar
import re
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app.pipeline import entity_match

# Config
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
FACT_NODE = "fact"


class RequiredItem(BaseModel):
    key: str
    label: str
    predicate: str  # a verified fact with this predicate proves the item
    subject: list[str] | None = None  # [type, key] of the thing it must be about; None means any
    grant: dict | None = None  # slice 5: a data source that could supply it, if someone grants access (source, scope, retention_days, agents, revoke)


class Due(BaseModel):
    every: str | None = None  # month or year
    day: int | None = None
    month: int | None = None
    fact: dict | None = None  # {subject: [type, key], predicates: [...]}: due when that fact's term ends


class Obligation(BaseModel):
    id: str
    title: str
    jurisdiction: str
    category: str  # tax, statutory, contract, renewal
    dri: str
    due: Due
    prepare_days: int
    note: str
    items: list[RequiredItem]


class Instance(BaseModel):
    """One obligation, due once: VAT for September 2026 is ob_vat:2026-09."""
    instance_id: str
    obligation: Obligation
    period: str | None  # YYYY-MM for a monthly one, YYYY for a yearly one, None for one due from a fact
    due_at: datetime
    prepare_by: datetime


# --- Dates

def on_day(year: int, month: int, day: int) -> datetime:
    """That day at midnight UTC; a day past the month's end is its last day (the 30th of February is the 28th or 29th)."""
    return datetime(year, month, min(day, calendar.monthrange(year, month)[1]), tzinfo=timezone.utc)


def month_before(year: int, month: int) -> str:
    return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def monthly(ob: Obligation, now: datetime) -> tuple[datetime, str]:
    """The next due day on or after today, and the month it covers."""
    due = on_day(now.year, now.month, ob.due.day)
    if due.date() < now.date():
        year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        due = on_day(year, month, ob.due.day)
    return due, month_before(due.year, due.month)


def yearly(ob: Obligation, now: datetime) -> tuple[datetime, str]:
    due = on_day(now.year, ob.due.month, ob.due.day)
    due = due if due.date() >= now.date() else on_day(now.year + 1, ob.due.month, ob.due.day)
    return due, str(due.year - 1)


def from_fact(lane, ob: Obligation) -> datetime | None:
    """When the verified term of the thing ends: the latest end among its facts, or None when no fact says so yet."""
    subject = entity_match.entity_id_of(*ob.due.fact["subject"])
    facts = [f for f in lane.graph.latest(FACT_NODE) if f["subject"]["entity_ref"] == subject and f["predicate"] in ob.due.fact["predicates"]]
    ends = [f["valid_to"][:10] for f in facts if f.get("valid_to")] + [d for f in facts for d in DATE.findall(f["value"]["normalized"])]
    return datetime.fromisoformat(max(ends)).replace(tzinfo=timezone.utc) if ends else None


def period_label(period: str | None) -> str:
    """2026-09 reads as September 2026, 2025 as 2025, and no period as nothing."""
    if not period:
        return ""
    if len(period) == 4:
        return f" · {period}"
    return f" · {datetime.strptime(period, '%Y-%m').strftime('%B %Y')}"


# --- Ids of a gap and its request

def safe(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def gap_id_of(instance_id: str, key: str) -> str:
    return f"gap_{safe(instance_id)}_{key}"


def request_id_of(instance_id: str, key: str) -> str:
    return "er_" + gap_id_of(instance_id, key).removeprefix("gap_")


# --- Instances

def obligations_of(seed: dict) -> list[Obligation]:
    return [Obligation.model_validate(ob) for ob in seed.get("readiness", {}).get("obligations", [])]


def instance_of(lane, ob: Obligation, now: datetime) -> Instance | None:
    """The next instance of one obligation. None when its due date is not known yet (no verified term for a renewal)."""
    if ob.due.every == "month":
        due, period = monthly(ob, now)
    elif ob.due.every == "year":
        due, period = yearly(ob, now)
    else:
        due, period = from_fact(lane, ob), None
    if due is None:
        return None
    return Instance(instance_id=f"{ob.id}:{period or due.date().isoformat()}", obligation=ob, period=period, due_at=due, prepare_by=due - timedelta(days=ob.prepare_days))


def current(lane, now: datetime) -> list[Instance]:
    """Every obligation's next instance, soonest first."""
    found = [instance_of(lane, ob, now) for ob in obligations_of(lane.seed)]
    return sorted((i for i in found if i is not None), key=lambda i: i.due_at)
