# event_log.py: a skill's runs as an XES event log (Research Lab P4), so its behaviour can be checked against its model:
# one trace per run (its outcome, the skill version it pinned), one event per step, named by the step's activity (P3),
# timed by the step, in the order the run took them. Standard XES 1.0 that pm4py, ProM and Disco read.
# Reading every run of a skill is an export, never the hot path. Used by: api/event_log_routes.py, research/conformance.py.
# Uses: activities.py.
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from app.pipeline import activities

# Config
XES = "http://www.xes-standard.org/"
EXTENSIONS = [("Concept", "concept"), ("Time", "time"), ("Lifecycle", "lifecycle")]


def runs_of(lane, skill_id: str) -> list[dict]:
    """Every recorded run that pinned this skill, oldest first."""
    found = [r for r in lane.records.list_kind("run") if (r.get("skill_ref") or {}).get("id") == skill_id]
    return sorted(found, key=lambda r: min((s["started_at"] for s in r.get("steps") or []), default=""))


def events_of(run: dict) -> list[tuple[str, datetime]]:
    """The run's activities and times, each step's own activity or, for a step recorded before P3, the one it stands for.
    Steps that share a moment keep their order: each is a microsecond after the one before it."""
    found, last = [], None
    for step in run.get("steps") or []:
        at = datetime.fromisoformat(str(step["started_at"]).replace("Z", "+00:00"))  # Python 3.10 reads no trailing Z
        at = at if last is None or at > last else last + timedelta(microseconds=1)
        found.append((step.get("activity_id") or activities.activity_of(step["kind"], step["decision"]), at))
        last = at
    return found


def to_xes(runs: list[dict], name: str) -> str:
    """The runs as one XES log named after the skill."""
    log = ET.Element("log", {"xes.version": "1.0", "xes.features": "nested-attributes", "xmlns": XES})
    for title, prefix in EXTENSIONS:
        ET.SubElement(log, "extension", {"name": title, "prefix": prefix, "uri": f"{XES}{prefix}.xesext"})
    ET.SubElement(log, "string", {"key": "concept:name", "value": name})
    for run in runs:
        trace = ET.SubElement(log, "trace")
        ET.SubElement(trace, "string", {"key": "concept:name", "value": run["run_id"]})
        ET.SubElement(trace, "string", {"key": "outcome", "value": str(run.get("outcome", ""))})
        ET.SubElement(trace, "int", {"key": "skill:version", "value": str((run.get("skill_ref") or {}).get("version", 0))})
        for activity, at in events_of(run):
            event = ET.SubElement(trace, "event")
            ET.SubElement(event, "string", {"key": "concept:name", "value": activity})
            ET.SubElement(event, "date", {"key": "time:timestamp", "value": at.isoformat()})
            ET.SubElement(event, "string", {"key": "lifecycle:transition", "value": "complete"})
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(log, encoding="unicode")
