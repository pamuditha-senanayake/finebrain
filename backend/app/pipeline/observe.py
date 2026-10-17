# observe.py: one JSON log line per event, and in-process counters per stage and outcome.
# Used by: capture_api.py, and every stage as it gets thicker. Uses: nothing local.
# Counters live in this process for now; a Prometheus export comes later.
import json
import logging
from collections import Counter

# Config
LOGGER_NAME = "finebrain"

logger = logging.getLogger(LOGGER_NAME)
counters: Counter[str] = Counter()


def log_event(stage: str, event: str, **fields) -> None:
    """One line a log tool can parse. Callers pass ids and codes only, never personal data."""
    logger.info(json.dumps({"stage": stage, "event": event, **fields}, default=str, sort_keys=True))


def count(name: str, amount: int = 1) -> None:
    """Add to a counter like s1.rejected.signature."""
    counters[name] += amount


def read_count(name: str) -> int:
    return counters[name]


def reset_counts() -> None:
    """Tests start from zero."""
    counters.clear()
