# distiller.py: the Distiller (step 13d), the memory's night shift at 03:00, after the 02:00 review. It writes the missing
# summaries (day, week, month per entity), merges duplicates of the same words, then scores every item, moves items between
# tiers (cold is archived) and ends raw bodies past their retention. Each night is kept and audited.
# Used by: memory_routes.py (ops/runDistiller), hq.py (the schedule), tests/test_summary.py, test_dupes.py. Uses: stages_summary.py, stages_dupes.py, stages_value.py, stages_tiers.py, stages_cold.py.
from datetime import datetime

from pydantic import BaseModel

from app.pipeline import stages_cold, stages_dupes, stages_summary, stages_tiers, stages_value

# Config
RUN_KIND = "distiller_run"


class DistillerRun(BaseModel):
    """What one night did, kept as the latest record."""
    at: datetime
    by: str
    summaries: dict[str, int]
    merged: int = 0
    scored: int
    moved: int
    raw_deleted: int


def distill(lane, summarizer, by: str) -> dict:
    """One night of the Distiller. summarizer is Claude Haiku with tools (lane.extract), or None for plain summaries."""
    # Step 1: summaries first, so tonight's scores and tiers already include them; then duplicates answer once
    written = stages_summary.ladder(lane, summarizer)
    merged = stages_dupes.merge(lane)

    # Step 2: score, place in tiers, end raw bodies past retention
    scored = stages_value.score_all(lane)
    moved = stages_tiers.move(lane).moved
    raw = stages_cold.sweep_raw(lane, apply=True, by=by)

    # Step 3: keep the night and audit it
    run = DistillerRun(at=lane.now, by=by, summaries=written, merged=merged, scored=scored, moved=moved, raw_deleted=raw["deleted"])
    lane.records.save(RUN_KIND, "latest", run)
    lane.audit.append(f"distiller:{lane.now.isoformat()}", "distiller.ran",
                      {"by": by, "at": lane.now.isoformat(), "reason": f"{sum(written.values())} summaries, {merged} duplicates, {scored} scored, {moved} moved, {raw['deleted']} raw ended"})
    return run.model_dump(mode="json")
