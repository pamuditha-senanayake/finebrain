# drift_eval.py: scores drift alarms against known drift points, as Adams et al. (PVLDB 2023, "An Experimental Evaluation of
# Process Concept Drift Detection") do: an alarm is a true detection when it falls in a lag window after a drift (a gradual
# drift spans its whole transition), each drift is found at most once, and every other alarm is false. Reports recall,
# delay in traces, the false alarm rate, precision and F1 (spec section 7.2). Also reads XES event logs into cases with
# the standard library, so the drift signal can run on any public log. Used by: scripts/research_drift_benchmark.py, tests.
# Uses: nothing local.
import re
import xml.etree.ElementTree as ET
from datetime import datetime

# Config
LAG = 500  # traces after a drift's start (or a gradual drift's end) in which an alarm counts as finding it
XES = "{http://www.xes-standard.org/}"
FRACTION = re.compile(r"(\.\d+)")


def score(alarms: list[int], drifts: list[tuple[int, int]], lag: int = LAG, natural: list[int] = ()) -> dict:
    """drifts are (start, end) case indexes; a sudden drift has start == end. An alarm that finds no drift but sits within the
    lag of an alarm the undrifted log also raises (`natural`) is a change in the real process: counted apart, not as false."""
    left, found = sorted(alarms), []
    for start, end in sorted(drifts):
        hit = next((a for a in left if start <= a <= end + lag), None)
        if hit is not None:
            left.remove(hit)
            found.append(hit - start)
    true, real = len(found), sum(any(abs(a - b) <= lag for b in natural) for a in left)
    alarms = [a for a in alarms if a not in left] + [a for a in left if not any(abs(a - b) <= lag for b in natural)]  # drop the real-process ones
    precision = true / len(alarms) if alarms else 1.0
    recall = true / len(drifts) if drifts else 1.0
    return {"drifts": len(drifts), "alarms": len(alarms), "natural": real, "found": true, "recall": recall, "delay_traces": sum(found) / true if true else None,
            "false_alarm_rate": (len(alarms) - true) / len(alarms) if alarms else 0.0, "precision": precision,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def drifts_of(points: list[int], shape: str) -> list[tuple[int, int]]:
    """A gradual drift's two points are its transition; sudden and recurring points are each a drift."""
    return [(points[0], points[-1])] if shape == "gradual" else [(p, p) for p in points]


def at(text: str | None) -> datetime | None:
    """An XES time. Python 3.10 reads neither a trailing Z nor more than six digits of a second, which real logs carry."""
    return datetime.fromisoformat(FRACTION.sub(lambda m: m.group(1)[:7], text.replace("Z", "+00:00"))) if text else None


def read_xes(path: str) -> list[dict]:
    """The log's cases in file order: each case's activities, and each activity's durations (completion minus start)."""
    cases, case = [], None
    for event, element in ET.iterparse(path, events=("start", "end")):
        tag = element.tag.removeprefix(XES)
        if event == "start" and tag == "trace":
            case = {"activities": [], "durations": {}}
        elif event == "end" and tag == "event" and case is not None:
            values = {child.get("key"): child.get("value") for child in element}
            name, started, done = values.get("concept:name"), at(values.get("start:timestamp")), at(values.get("time:timestamp"))
            case["activities"].append(name)
            if started and done:
                case["durations"].setdefault(name, []).append((done - started).total_seconds())
            element.clear()
        elif event == "end" and tag == "trace" and case is not None:
            cases.append(case)
            case = None
            element.clear()
    return cases
