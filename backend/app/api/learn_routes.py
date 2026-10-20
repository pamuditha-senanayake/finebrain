# learn_routes.py: Lane C (step 15) on the Finebase HQ API. S13's weekly counting (the consumer of runs.completed,
# sample history for a tenant with none, a back-fill of earlier runs), the spike check after each count, and
# POST ops/markTrendKnown, ops/markRunWrong, ops/draftFix (Skillify) and ops/runOvernightReview. Used by: routes.py (register).
# Uses: stages_learn.py, stages_spike.py, trend_views.py, run_marks.py, skillify.py, nightly.py.
from fastapi import FastAPI, Header, HTTPException, Request

from app.api import nightly, run_marks, skillify
from app.api.trend_views import tell_owner
from app.pipeline import stages_learn, stages_spike
from app.pipeline.observe import log_event

# Config
MAY_MARK_KNOWN = {"L1", "L2"}
MAY_DRAFT = {"L1", "L2"}  # a draft costs a model call; L3 marks a run wrong and a steward drafts the fix, or the nightly review does


def raise_spikes(lane, series: list[tuple[str, str]]) -> None:
    """Check the weeks a count just changed: a spike shows as soon as the count that makes it lands."""
    for metric, segment in series:
        if trend := stages_spike.check_series(lane, metric, segment, lane.now):
            tell_owner(lane, trend)


def start_counting(lane) -> None:
    """Sample history first, so real runs add to it rather than being hidden by it; then earlier runs; then one check."""
    sampled = stages_learn.load_sample(lane, lane.seed.get("sample_counts") or {})
    counted = stages_learn.count_existing(lane)
    found = stages_spike.check(lane, lane.now)
    for trend in found:
        tell_owner(lane, trend)
    log_event("S13", "counts_ready", sample_weeks=sampled, back_filled=counted, trends_found=len(found))


def register(app: FastAPI, lane, check, drafter=None) -> None:
    """S13's consumer, the start-up back-fill, Mark as known, Mark as wrong, Draft a fix (drafter: Claude Sonnet with tools,
    or None) and the overnight review (it groups with lane.resolve, Claude Opus with tools). Before the general ops route."""
    lane.bus.subscribe("runs.completed", "counts", "S13", lambda envelope: raise_spikes(lane, stages_learn.on_run(lane, envelope)))
    start_counting(lane)

    @app.post("/api/t/{tenant}/ops/markTrendKnown")
    async def mark_known(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        if lane.seed["people"][x_persona]["tier"] not in MAY_MARK_KNOWN:
            raise HTTPException(403, "not_a_steward")
        try:
            stages_spike.mark_known(lane, str((await request.json()).get("id", "")), x_persona, lane.now)
        except LookupError:
            raise HTTPException(404, "not_found") from None
        except stages_spike.NotPossible as reason:
            raise HTTPException(409, str(reason)) from None
        return {"ok": True}

    @app.post("/api/t/{tenant}/ops/markRunWrong")
    async def mark_wrong(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)  # anyone who sees a wrong outcome may say so
        body = await request.json()
        try:
            _, counted = run_marks.mark_wrong(lane, str(body.get("runId", "")), x_persona, str(body.get("note") or ""))
        except LookupError:
            raise HTTPException(404, "not_found") from None
        except run_marks.NotPossible as reason:
            raise HTTPException(409, str(reason)) from None
        raise_spikes(lane, counted)
        return {"ok": True}

    @app.post("/api/t/{tenant}/ops/draftFix")
    async def draft_fix(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        if lane.seed["people"][x_persona]["tier"] not in MAY_DRAFT:
            raise HTTPException(403, "not_a_steward")
        try:
            return skillify.draft_fix(lane, drafter, str((await request.json()).get("runId", "")), x_persona)
        except LookupError:
            raise HTTPException(404, "not_found") from None
        except skillify.NotPossible as reason:
            raise HTTPException(503 if str(reason) == "no_model" else 409, str(reason)) from None

    @app.post("/api/t/{tenant}/ops/runOvernightReview")
    def run_review(tenant: str, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        if lane.seed["people"][x_persona]["tier"] not in MAY_DRAFT:
            raise HTTPException(403, "not_a_steward")
        digest = nightly.review(lane, drafter, lane.resolve, x_persona)
        return {"ok": True, "runs": digest["runs"], "failures": digest["failures"], "items": len(digest["items"])}
