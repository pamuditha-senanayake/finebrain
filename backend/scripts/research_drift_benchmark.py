# research_drift_benchmark.py: a dev script. Runs the S13 drift signal on the public "Everything Real but the Drift" logs
# (Padella and Vinci, Zenodo 10.5281/zenodo.21005862, CC BY 4.0: 5 real logs, each with control-flow, slow-down and
# speed-up drift, sudden, gradual and recurring) and scores it as Adams et al. do:
#   uv run python scripts/research_drift_benchmark.py <unzipped drifted_logs folder> <out.json>
# The detector's settings are fixed in drift_signal.py, never tuned on these logs. Real logs drift on their own, so each
# log is scored twice: strictly (every unmatched alarm is false), and with an unmatched alarm that its undrifted baseline also
# raises within the lag window set apart as a change in the real process, not a false alarm (recall is the same in both).
import json
import re
import sys
import time
from pathlib import Path

from app.pipeline import drift_signal
from app.research import drift_eval

# Config
POINTS = re.compile(r"Change point\(s\):\*\* \[([^\]]*)\]")
SHAPE = re.compile(r"\*\*Shape:\*\* (\w+)")


def baseline_alarms(root: Path, log: str, cache: dict) -> list[int]:
    if log not in cache:
        cache[log] = [a.at for a in drift_signal.detect(drift_eval.read_xes(str(root / "baselines" / f"{log}_baseline.xes")))]
    return cache[log]


def one(root: Path, readme: Path, cache: dict) -> dict | None:
    text, perspective, shape, log = readme.read_text(), readme.parts[-4], readme.parts[-3], readme.parts[-2]
    points = POINTS.search(text)
    if not points:
        return {"log": log, "perspective": perspective, "shape": shape, "skipped": "its README names no change points"}
    drifts = drift_eval.drifts_of([int(p) for p in points.group(1).split(",")], SHAPE.search(text).group(1))
    started = time.time()
    alarms = [a for a in drift_signal.detect(drift_eval.read_xes(str(next(readme.parent.glob("*.xes")))))]
    at = [a.at for a in alarms]
    return {"log": log, "perspective": perspective, "shape": shape, "drifts": drifts, "alarms": [(a.at, a.feature) for a in alarms],
            "strict": drift_eval.score(at, drifts), "without_natural": drift_eval.score(at, drifts, natural=baseline_alarms(root, log, cache)),
            "seconds": round(time.time() - started, 1)}


def summary(rows: list[dict], key: str) -> dict:
    scored = [r for r in rows if "skipped" not in r]
    found, drifts, alarms = (sum(r[key][k] for r in scored) for k in ("found", "drifts", "alarms"))
    delays = [r[key]["delay_traces"] * r[key]["found"] for r in scored if r[key]["found"]]
    return {"logs": len(scored), "recall": found / drifts, "delay_traces": sum(delays) / found if found else None,
            "false_alarm_rate": (alarms - found) / alarms if alarms else 0.0, "precision": found / alarms if alarms else 1.0}


if __name__ == "__main__":
    root, cache = Path(sys.argv[1]), {}
    rows = [one(root, readme, cache) for readme in sorted(root.glob("*/*/*/README.md"))]
    groups = sorted({(r["perspective"], r["shape"]) for r in rows})
    result = {"settings": {"window": drift_signal.WINDOW, "step": drift_signal.STEP, "z_bar": drift_signal.Z_BAR, "lag": drift_eval.LAG},
              "overall": {k: summary(rows, k) for k in ("strict", "without_natural")},
              "by_group": {f"{p}/{s}": {k: summary([r for r in rows if (r["perspective"], r["shape"]) == (p, s)], k) for k in ("strict", "without_natural")} for p, s in groups},
              "baseline_alarms": {log: len(a) for log, a in cache.items()}, "logs": rows}
    Path(sys.argv[2]).write_text(json.dumps(result, indent=1))
    print(json.dumps({k: result[k] for k in ("settings", "overall", "baseline_alarms")}, indent=1))
