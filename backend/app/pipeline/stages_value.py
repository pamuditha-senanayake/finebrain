# stages_value.py: the value score of every item (step 13c), which decides what stays hot and what moves down a tier.
# value = use x recency x risk x trust x links. Use counts the runs and answers that cited it; recency halves every 30 days
# since its last use (or since it was recorded); risk keeps legal and money matters; trust favours verified facts and
# policies; links count the entities it is about. A closed item keeps a tenth: it is history now.
# Used by: api/memory_routes.py, api/hq.py (nightly), tests/test_value.py. Uses: contracts_run.py.
import json
import math
from datetime import datetime

from app.pipeline.contracts_run import RunRecord

# Config
HALF_LIFE_DAYS = 30
MIN_RECENCY = 0.05  # an old item never scores 0: risk or trust may still keep it
RISKY_KINDS, RISKY_DOMAINS, RISK = {"policy"}, {"legal", "finance"}, 2.0
TRUST = {"fact": 1.5, "policy": 1.5, "chunk": 1.0, "summary": 0.8}  # anything else counts 1.0
LINK_STEP, MOST_LINKS = 0.25, 4
CLOSED = 0.1


# --- The score

def moment(text) -> datetime:
    """A stored time; Postgres gives them back ending in Z, which Python 3.10 cannot read."""
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def value_of(item: dict, uses: int, last_used: datetime | None, now: datetime) -> float:
    """One item's score. Every factor is 1 for an ordinary item, so they read as "how many times more"."""
    use = 1 + math.log2(1 + uses)
    since = last_used or moment(item["recorded_at"])
    recency = max(MIN_RECENCY, 0.5 ** (max((now - since).days, 0) / HALF_LIFE_DAYS))
    risk = RISK if item["kind"] in RISKY_KINDS or item.get("domain") in RISKY_DOMAINS else 1.0
    trust = TRUST.get(item["kind"], 1.0)
    links = 1 + LINK_STEP * min(len(item.get("entity_ids") or []), MOST_LINKS)
    closed = CLOSED if item.get("valid_to") and moment(item["valid_to"]) <= now else 1.0
    return round(use * recency * risk * trust * links * closed, 4)


def score_all(lane) -> int:
    """Score every item and store it. Returns how many were scored."""
    rows = lane.chunks.value_rows()
    uses = lane.uses.uses_of([row["item_id"] for row in rows])
    values = {row["item_id"]: value_of(row, *uses.get(row["item_id"], (0, None)), lane.now) for row in rows}
    lane.chunks.set_values(values, lane.now)
    return len(values)


# --- Uses

def cited_by_run(lane, run: dict) -> list[str]:
    """The items a run's judgment cited, read through its trace. None when the trace is gone."""
    try:
        return list(json.loads(lane.object_store[run["trace_object_uri"]])["action"]["citations"])
    except (KeyError, ValueError, TypeError):
        return []


def note_run(lane, run: dict) -> int:
    """Count a run's citations, once each. Returns how many were new."""
    at = moment(run["steps"][-1]["started_at"]) if run.get("steps") else lane.now
    return sum(lane.uses.note(item_id, run["run_id"], at) for item_id in cited_by_run(lane, run))


def on_run(lane, envelope) -> None:
    """The consumer of runs.completed."""
    note_run(lane, RunRecord.model_validate(envelope.payload).model_dump(mode="json"))


def note_answer(lane, used_by: str, cited: list[str], at: datetime) -> int:
    """Count an Ask answer's citations (used_by names the turn). Returns how many were new."""
    return sum(lane.uses.note(item_id, used_by, at) for item_id in cited)
