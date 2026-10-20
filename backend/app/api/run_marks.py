# run_marks.py: Mark as wrong on Finebase HQ (step 15). Anyone who sees a wrong outcome records what went wrong. The note
# stays on the run (a run_mark record beside the K10 record, which only S10 writes), the agent's DRI is told, it is
# audited, and it counts as "Marked wrong" for the agent in the week it was marked. The nightly review reads these notes.
# Used by: learn_routes.py (ops/markRunWrong), tests/test_marks.py (views.py reads the run_mark records). Uses: studio_changes.py (notify), lists_rows.py, views.py, stages_learn.py.
from datetime import datetime

from pydantic import BaseModel

from app.api.lists_rows import cache_of
from app.api.studio_changes import notify
from app.api.views import run_view
from app.pipeline import stages_learn

# Config
MARK_KIND = "run_mark"
NOTE_MAX = 2000


class RunMark(BaseModel):
    run_id: str
    by: str
    at: datetime
    note: str


class NotPossible(Exception):
    """The run cannot be marked this way."""


def mark_of(lane, run_id: str) -> dict | None:
    return lane.records.load(MARK_KIND, run_id)


def mark_wrong(lane, run_id: str, by: str, note: str) -> tuple[RunMark, list[tuple[str, str]]]:
    """Record the note once. Returns the mark and the series it newly counted in, for the spike check."""
    # Step 1: a recorded run, once, with a note
    run = lane.records.load("run", run_id)
    if run is None:
        raise LookupError(run_id)
    if mark_of(lane, run_id):
        raise NotPossible("already_marked")
    if not note.strip():
        raise NotPossible("say_what_went_wrong")

    # Step 2: keep the note, and rebuild the run's row so lists show it
    mark = RunMark(run_id=run_id, by=by, at=lane.now, note=note.strip()[:NOTE_MAX])
    lane.records.save(MARK_KIND, run_id, mark)
    cache_of(lane)["runs"].pop(run_id, None)

    # Step 3: tell the agent's DRI, audit it, and count it
    agent = lane.seed.get("agents", {}).get(run["agent_id"], {})
    dri = (agent.get("studio") or {}).get("dri")
    notify(lane, dri, f"Marked wrong: {run_view(lane, run).subject}", f"{stages_learn.agent_name(lane, run['agent_id'])}. {mark.note}", f"/l3/runs/{run_id}")
    lane.audit.append(f"run:{run_id}:marked_wrong", "run.marked_wrong", {"by": by, "at": lane.now.isoformat(), "reason": mark.note})
    return mark, stages_learn.count_mark(lane, run, mark.at)
