# s7_world.py: helpers for S7 to S10 tests. The whole pipeline runs for real (S1 to S10, with S9's runners as they are
# today: the stand-in payment gateway and email), the shop is the real database, and the model is scripted or real Claude.
# Uses: orchestrate.py, tests/s5_world.py, tests/s6_world.py.
import json

from app.pipeline import orchestrate
from tests.s5_world import make_lane, visitor_says


def full_lane(make_adapters=None, seed: dict | None = None):
    """make_lane with S4's own consumer back on, so every task runs S4 to S10 as in production."""
    lane = make_lane(make_adapters, seed=seed)
    lane.bus.subscribe("tasks.created", "worker", "S4", lambda envelope: orchestrate.on_task(lane, envelope))
    return lane


def says(lane, message: dict, **who) -> None:
    visitor_says(lane, message, **who)


def runs(lane) -> dict[str, list[str]]:
    """Each run's outcomes in the order S10 recorded them."""
    seen: dict[str, list[str]] = {}
    for envelope in lane.bus.topics.get("runs.completed", []):
        seen.setdefault(envelope.payload["run_id"], []).append(envelope.payload["outcome"])
    return seen


def last_record(lane) -> dict:
    return lane.bus.topics["runs.completed"][-1].payload


def actions(lane) -> list[tuple[str, str]]:
    """S9's results: which tool, and how it went."""
    return [(e.payload["tool_id"], e.payload["status"]) for e in lane.bus.topics.get("actions.executed", [])]


def verdicts(lane) -> list[dict]:
    """S7's verdicts, from the run traces S10 wrote."""
    return [json.loads(lane.object_store[uri])["verdict"] for uri in sorted(lane.object_store) if "/traces/" in uri]
