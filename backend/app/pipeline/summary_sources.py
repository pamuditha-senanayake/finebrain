# summary_sources.py: what the summary ladder (step 13d) summarizes, per entity. A day reads the chunks and facts recorded
# that day and the runs started that day, through the entities their messages name; a week reads its day summaries and a
# month its week summaries. Each source is {"id", "text", "sensitivity", "domain"}. Used by: stages_summary.py, tests/test_summary.py.
# Uses: run_steps.py (signal_of), stages_value.py (moment).
import json
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from app.pipeline.run_steps import signal_of
from app.pipeline.stages_value import moment

# Config
SUMMARY_PREFIX = "sum_"
MOST_CHARS = 600  # of one source, so a busy entity's day still fits one prompt


def summary_id(level: str, entity_id: str, period: str) -> str:
    return f"{SUMMARY_PREFIX}{level}_{entity_id}_{period}"


def local_day(text, zone: str) -> date:
    return moment(text).astimezone(ZoneInfo(zone)).date()


def add(found: dict, entity_ids, source: dict) -> None:
    for entity_id in entity_ids or []:
        found.setdefault(entity_id, []).append(source)


def chunk_sources(lane, day: date, zone: str, found: dict) -> None:
    """Chunks and facts recorded that day, still true, about at least one entity. Summaries never summarize themselves."""
    for row in lane.chunks.value_rows():
        if row["item_id"].startswith(SUMMARY_PREFIX) or row.get("valid_to") or local_day(row["recorded_at"], zone) != day or not row.get("entity_ids"):
            continue
        item = lane.chunks.full(row["item_id"])[0]
        add(found, item["entity_ids"], {"id": item["item_id"], "text": item["text"][:MOST_CHARS], "sensitivity": item.get("sensitivity", "internal"), "domain": item.get("domain")})


def run_sources(lane, day: date, zone: str, found: dict) -> None:
    """Runs started that day: what was asked (masked) and what the agent did, under the entities the message named."""
    for run in lane.records.list_kind("run"):
        if not run.get("steps") or local_day(run["steps"][0]["started_at"], zone) != day:
            continue
        try:
            trace = json.loads(lane.object_store[run["trace_object_uri"]])
            signal = signal_of(lane, trace["task"]["signal_ids"][0])
        except (KeyError, ValueError, IndexError):
            continue  # its trace or message can no longer be read
        if signal is None:
            continue
        action = trace.get("action") or {}
        text = f"Run {run['run_id']}: {action.get('action_type', 'no action')} ({run['outcome']}). Message: {(signal.text_masked or '')[:MOST_CHARS]}"
        add(found, signal.entity_ids, {"id": run["run_id"], "text": text, "sensitivity": signal.sensitivity, "domain": signal.domain})


def day_sources(lane, day: date) -> dict[str, list[dict]]:
    zone = lane.seed.get("timezone", "UTC")
    found: dict[str, list[dict]] = {}
    chunk_sources(lane, day, zone, found)
    run_sources(lane, day, zone, found)
    return found


def rollup_sources(lane, level: str, periods: list[str]) -> dict[str, list[dict]]:
    """The summaries one level down, per entity, for these periods (a week's days, or a month's weeks)."""
    found: dict[str, list[dict]] = {}
    wanted = {f"_{period}" for period in periods}
    for row in lane.chunks.value_rows():
        if row["item_id"].startswith(f"{SUMMARY_PREFIX}{level}_") and any(row["item_id"].endswith(end) for end in wanted) and not row.get("valid_to"):
            item = lane.chunks.full(row["item_id"])[0]
            add(found, item["entity_ids"], {"id": item["item_id"], "text": item["text"], "sensitivity": item.get("sensitivity", "internal"), "domain": item.get("domain")})
    return found


def weeks_in(month_start: date) -> list[str]:
    """The Mondays of the weeks that start in this month."""
    first = month_start + timedelta(days=(7 - month_start.weekday()) % 7)
    return [str(first + timedelta(weeks=n)) for n in range(5) if (first + timedelta(weeks=n)).month == month_start.month]
