# stages_learn.py: S13's weekly counts (step 15). Every finished run adds one to its week: requests per skill, and
# escalations per agent, each split by channel. The spike check reads these counts. Weeks start on Monday in the
# tenant's time zone. Used by: api/learn_routes.py, stages_spike.py, tests/test_counts.py. Uses: run_steps.py (signal_of), contracts_run.py.
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.pipeline.contracts_run import RunRecord
from app.pipeline.run_steps import signal_of

# Config
ESCALATED = {"escalated", "awaiting_approval"}  # both wait on a person, as the Escalations screen shows them
UNKNOWN_CHANNEL = "unknown channel"  # a run whose trace or signal can no longer be read


# --- Helpers

def week_of(moment: datetime, zone: str) -> date:
    """The Monday of the week this moment falls in, on the tenant's calendar."""
    local = moment.astimezone(ZoneInfo(zone)).date()
    return local - timedelta(days=local.weekday())


def zone_of(lane) -> str:
    return lane.seed.get("timezone", "UTC")


def agent_name(lane, agent_id: str) -> str:
    agent = lane.seed.get("agents", {}).get(agent_id, {})
    return (agent.get("studio") or {}).get("name") or agent_id


def skill_name(lane, skill_id: str) -> str:
    return next((skill.get("name", skill_id) for skill in lane.seed.get("skills", []) if skill.get("id") == skill_id), skill_id)


def channel_of(lane, run: dict) -> str:
    """The channel of the message that started the run, read through its trace."""
    try:
        trace = json.loads(lane.object_store[run["trace_object_uri"]])
        signal = signal_of(lane, trace["task"]["signal_ids"][0])
    except (KeyError, ValueError, IndexError, TypeError):
        return UNKNOWN_CHANNEL
    return signal.channel if signal else UNKNOWN_CHANNEL


def series_of(lane, run: dict) -> list[tuple[str, str]]:
    """The (metric, segment) pairs one run counts towards."""
    channel = channel_of(lane, run)
    found = [("Requests", f"{skill_name(lane, run['skill_ref']['id'])}, {channel}")]
    if run["outcome"] in ESCALATED:
        found.append(("Escalations", f"{agent_name(lane, run['agent_id'])}, {channel}"))
    return found


# --- Counting

def count_run(lane, run: dict) -> list[tuple[str, str]]:
    """Count one run (a stored K10 record) in its week. Returns the series it newly counted in: none when already counted."""
    if not run.get("steps"):
        return []
    started = datetime.fromisoformat(str(run["steps"][0]["started_at"]).replace("Z", "+00:00"))
    week = week_of(started, zone_of(lane))
    return [(metric, segment) for metric, segment in series_of(lane, run) if lane.counts.add(metric, segment, week, run["run_id"])]


def on_run(lane, envelope) -> list[tuple[str, str]]:
    """S13's consumer of runs.completed. A run that pauses for approval and then finishes counts once per series."""
    return count_run(lane, RunRecord.model_validate(envelope.payload).model_dump(mode="json"))


def count_existing(lane) -> int:
    """Back-fill: count every run already recorded. Safe to run on every start. Returns how many counts it added."""
    return sum(len(count_run(lane, run)) for run in lane.records.list_kind("run"))


def load_sample(lane, sample: dict) -> int:
    """Sample history for a tenant too new to have any: one count per week, ending on the week given. Returns weeks written."""
    if not sample:
        return 0
    last = date.fromisoformat(sample["weeks_ending"])
    written = 0
    for row in sample["series"]:
        first = last - timedelta(weeks=len(row["weeks"]) - 1)
        for index, value in enumerate(row["weeks"]):
            lane.counts.add_sample(row["metric"], row["segment"], first + timedelta(weeks=index), value)
            written += 1
    return written
