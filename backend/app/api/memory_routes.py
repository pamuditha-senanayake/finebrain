# memory_routes.py: step 13 (memory and storage) on the Finebase HQ API. It starts the value score and the tiers (13c):
# the consumer that counts each finished run's citations, a back-fill of runs and Ask answers recorded before, one
# scoring pass and one tier pass, so every item has a value and a tier from the start; and POST ops/runDistiller (13d).
# Used by: routes.py (register), ask.py (answer_id). Uses: stages_value.py, stages_tiers.py, distiller.py, ask_memory.py.
from fastapi import FastAPI, Header, HTTPException

from app.api import ask_memory, distiller
from app.pipeline import stages_tiers, stages_value
from app.pipeline.observe import log_event

# Config
MAY_RUN = {"L1", "L2"}  # the Distiller calls Claude once per entity with news


def answer_id(conversation_id: str, at) -> str:
    """One Ask turn, the same whether it is counted live or back-filled."""
    return f"ask:{conversation_id}:{stages_value.moment(at).isoformat()}"


def note_answers(lane) -> int:
    """Back-fill: every Ask turn ever answered, once."""
    noted = 0
    for latest in lane.records.list_kind(ask_memory.KIND):
        for turn in lane.records.history(ask_memory.KIND, latest["conversation_id"]):
            noted += stages_value.note_answer(lane, answer_id(turn["conversation_id"], turn["at"]), turn["cited"], stages_value.moment(turn["at"]))
    return noted


def register(app: FastAPI, lane, check) -> None:
    """Count citations from now on and from before, then score and place every item. All of it is safe to repeat."""
    # Step 1: new runs count their citations as they finish (Ask counts its own, in ask.py)
    lane.bus.subscribe("runs.completed", "uses", "S13", lambda envelope: stages_value.on_run(lane, envelope))

    # Step 2: citations recorded before counting existed
    from_runs = sum(stages_value.note_run(lane, run) for run in lane.records.list_kind("run"))
    from_answers = note_answers(lane)

    # Step 3: a score and a tier for every item now; the Distiller keeps both current every night
    scored = stages_value.score_all(lane)
    tiers = stages_tiers.move(lane)
    log_event("S13", "values_ready", uses_from_runs=from_runs, uses_from_answers=from_answers, scored=scored, hot=tiers.hot, warm=tiers.warm, cold=tiers.cold)

    @app.post("/api/t/{tenant}/ops/runDistiller")
    def run_distiller(tenant: str, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        if lane.seed["people"][x_persona]["tier"] not in MAY_RUN:
            raise HTTPException(403, "not_a_steward")
        return {"ok": True, **distiller.distill(lane, lane.extract, x_persona)}  # lane.extract: Claude Haiku with tools, or None
