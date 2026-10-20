# memory_routes.py: step 13 (memory and storage) on the Finebase HQ API. For now it starts the value score (13c): the
# consumer that counts each finished run's citations, a back-fill of runs and Ask answers recorded before, and one
# scoring pass, so every item has a value from the start. Used by: routes.py (register). Uses: stages_value.py, ask_memory.py.
from fastapi import FastAPI

from app.api import ask_memory
from app.pipeline import stages_value
from app.pipeline.observe import log_event


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
    """Count citations from now on and from before, then score every item. All of it is safe to repeat."""
    # Step 1: new runs count their citations as they finish (Ask counts its own, in ask.py)
    lane.bus.subscribe("runs.completed", "uses", "S13", lambda envelope: stages_value.on_run(lane, envelope))

    # Step 2: citations recorded before counting existed
    from_runs = sum(stages_value.note_run(lane, run) for run in lane.records.list_kind("run"))
    from_answers = note_answers(lane)

    # Step 3: a score for every item now; the nightly pass keeps it current
    scored = stages_value.score_all(lane)
    log_event("S13", "values_ready", uses_from_runs=from_runs, uses_from_answers=from_answers, scored=scored)
