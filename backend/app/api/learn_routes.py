# learn_routes.py: Lane C (step 15) on the Finebase HQ API. For now it starts S13's weekly counting: the consumer of
# runs.completed, sample history for a tenant with none, and a back-fill of runs recorded before counting existed.
# Used by: routes.py (register). Uses: stages_learn.py.
from fastapi import FastAPI

from app.pipeline import stages_learn
from app.pipeline.observe import log_event


def register(app: FastAPI, lane, check) -> None:
    """Count every finished run from now on, and the ones already recorded. Both are safe to repeat."""
    # Step 1: new runs count as they finish
    lane.bus.subscribe("runs.completed", "counts", "S13", lambda envelope: stages_learn.on_run(lane, envelope))

    # Step 2: sample history first, so real runs add to it rather than being hidden by it
    sampled = stages_learn.load_sample(lane, lane.seed.get("sample_counts") or {})

    # Step 3: runs recorded before counting existed
    counted = stages_learn.count_existing(lane)
    log_event("S13", "counts_ready", sample_weeks=sampled, back_filled=counted)
