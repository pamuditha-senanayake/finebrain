# observe.py: one JSON log line per event, and in-process counters per stage and outcome.
# Used by: capture_api.py, and every stage as it gets thicker. Uses: nothing local.
# Counters live in this process for now; a Prometheus export comes later.
import json
import logging
import os
from collections import Counter
from pathlib import Path

# Config
LOGGER_NAME = "finebrain"
SEAM_LOG_DIR = os.environ.get("SEAM_LOG_DIR")  # when set, each seam appends what came in and went out to <stage>.jsonl

logger = logging.getLogger(LOGGER_NAME)
counters: Counter[str] = Counter()
flags: dict[str, bool] = {}  # health flags, like recorder_delayed, read by the live stream
last_seen: dict[str, str] = {}  # when something last happened, like a connector's last event


def log_event(stage: str, event: str, **fields) -> None:
    """One line a log tool can parse. Callers pass ids and codes only, never personal data."""
    logger.info(json.dumps({"stage": stage, "event": event, **fields}, default=str, sort_keys=True))


def log_seam(stage: str, came_in: dict, went_out: dict) -> None:
    """One debug line per seam, matching its contract, kept on disk so a run can be read back later."""
    log_event(stage, "seam", came_in=came_in, went_out=went_out)
    if not SEAM_LOG_DIR:
        return
    Path(SEAM_LOG_DIR).mkdir(parents=True, exist_ok=True)
    with open(Path(SEAM_LOG_DIR) / f"{stage}.jsonl", "a", encoding="utf-8") as seam_file:
        seam_file.write(json.dumps({"in": came_in, "out": went_out}, default=str, sort_keys=True) + "\n")


def count(name: str, amount: int = 1) -> None:
    """Add to a counter like s1.rejected.signature."""
    counters[name] += amount


def read_count(name: str) -> int:
    return counters[name]


def reset_counts() -> None:
    """Tests start from zero."""
    counters.clear()
    flags.clear()
    last_seen.clear()


def set_flag(name: str, value: bool) -> None:
    flags[name] = value


def read_flag(name: str) -> bool:
    return flags.get(name, False)


def touch(name: str, at: str) -> None:
    last_seen[name] = at


def read_last_seen(name: str) -> str | None:
    return last_seen.get(name)
