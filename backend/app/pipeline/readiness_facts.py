# readiness_facts.py: step 16, how ready an obligation is. A required item is proven by a verified fact (step 14's vault) with its
# predicate or uploaded to answer its request, about the right thing, true now, and for a monthly or yearly one about that period. Readiness is never
# stored: it is worked out from the facts each time, so retiring the evidence makes the gap come back on its own.
# Used by: api/ready_views.py, tests/test_ready.py. Uses: readiness_model.py, entity_match.py.
from datetime import datetime

from app.pipeline import entity_match, readiness_model
from app.pipeline.readiness_model import FACT_NODE, Instance, RequiredItem

# Config
RED_WITHIN_DAYS = 7  # this close to the due day, anything short of ready is red (the console's rule, lib/governance/readiness.ts)
RED_BELOW = 50  # below this percent ready it is red whatever the date


def true_now(fact: dict, now: datetime) -> bool:
    return fact.get("status") != "superseded" and (not fact.get("valid_to") or datetime.fromisoformat(fact["valid_to"]) > now)


def about_period(fact: dict, period: str | None) -> bool:
    """A fact covers a period when it starts in it, or names it in its value (a September invoice total says 2026-09)."""
    if period is None:
        return True
    value = f"{fact['value'].get('normalized', '')} {fact['value'].get('raw', '')}"
    return str(fact.get("valid_from", "")).startswith(period) or period in value


def proven_by(lane, instance: Instance, item: RequiredItem, now: datetime) -> str | None:
    """The id of a verified fact that proves this item, or None: that is a gap."""
    subject = entity_match.entity_id_of(*item.subject) if item.subject else None
    request_id = readiness_model.request_id_of(instance.instance_id, item.key)
    for fact in lane.graph.latest(FACT_NODE):
        named = fact["predicate"] == item.predicate or fact.get("answers") == request_id  # the predicate, or uploaded to answer this request
        if named and (subject is None or fact["subject"]["entity_ref"] == subject) and true_now(fact, now) and about_period(fact, instance.period):
            return fact["item_id"]
    return None


def status_of(ready: int, due_at: datetime, now: datetime) -> str:
    """green when every item is proven; red when close to the due day or less than half ready; amber otherwise."""
    if ready == 100:
        return "green"
    return "red" if (due_at - now).days <= RED_WITHIN_DAYS or ready < RED_BELOW else "amber"


def readiness_of(lane, instance: Instance, now: datetime) -> tuple[list[tuple[RequiredItem, str | None]], int, str]:
    """Each item with the fact that proves it (or None), the percent proven, and the status."""
    proven = [(item, proven_by(lane, instance, item, now)) for item in instance.obligation.items]
    ready = round(100 * sum(fact_id is not None for _, fact_id in proven) / len(proven)) if proven else 100
    return proven, ready, status_of(ready, instance.due_at, now)
