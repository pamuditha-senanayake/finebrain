# experiment_routes.py: create, estimate, start, follow and read Lab experiments. Creating checks everything a run needs
# (a locked preregistration that still holds, a pack of the right kind, conditions Finebrain can run, a cap inside the
# limit) and saves the cost estimate; starting runs in one background worker per process; progress streams as SSE.
# Used by: research/routes.py. Uses: research/runner.py, research/results.py, research/kinds.py, research/prereg.py.
import asyncio
import hashlib
import json
import subprocess
import threading
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.research import experiment_store, freshness_lab, kinds, prereg, results, runner, security_lab
from app.research.contracts import Experiment, Paper

# Config
MAX_BUDGET_USD = 40.0  # the most one run may spend without a code change
TERMINAL = {"finished", "failed", "invalid_run", "budget_reached"}
PAPER_FOR_KIND = kinds.PAPER_FOR_KIND  # the kinds the Lab can run today
KIND_FOR_PAPER = {paper: kind for kind, paper in PAPER_FOR_KIND.items()}
STREAM_SECONDS = 2
RUN_ONE_AT_A_TIME = threading.Semaphore(1)  # lab load never starves the product: one experiment per process


class CreateBody(BaseModel):
    paper: Paper
    pack_id: str = Field(alias="packId")
    prereg_id: str = Field(alias="preregId")
    conditions: list[str]
    seeds: list[int] = [1, 2, 3]
    trials: int = Field(default=1, ge=1, le=8)
    model: str = "claude-haiku-5-5"
    budget_usd: float = Field(alias="budgetUsd", gt=0)


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def problems_with(body: CreateBody, pack, locked) -> list[str]:
    """Everything that would make the run unreadable, named before any money is spent."""
    found = [] if pack else ["pack not found"]
    found += [] if locked and locked.locked_at and prereg.holds(locked) else ["the preregistration must be locked first"]
    if pack and PAPER_FOR_KIND.get(pack.kind) != body.paper:
        found.append(f"a {pack.kind} pack cannot run for the {body.paper} paper yet")
    if locked and locked.paper != body.paper:
        found.append("the preregistration is for another paper")
    kind = kinds.KINDS.get(KIND_FOR_PAPER.get(body.paper, ""))
    found += [f"{c}: {kind.unavailable.get(c, 'not a condition') if kind else 'not a condition'}" for c in body.conditions if not kind or c not in kind.conditions]
    named = {c for h in (locked.hypotheses if locked else []) for c in h.conditions}
    found += [f"the preregistration compares {c}, which this run leaves out" for c in sorted(named - set(body.conditions))]
    found += [] if body.model in runner.PRICES else [f"unknown model {body.model}"]
    found += [] if body.budget_usd <= MAX_BUDGET_USD else [f"the cap is at most {MAX_BUDGET_USD} dollars"]
    return found + ([] if body.conditions and body.seeds else ["choose at least one condition and one seed"])


def register(app: FastAPI, check, experiments, packs, preregs, load_pack, parts, worker_stores) -> None:
    """`experiments()`, `packs()` and `preregs()` are the stores; `load_pack(id)` reads and parses a stored pack;
    `worker_stores()` opens the background worker's own stores, so a long run never holds the requests' connection."""

    def start_worker(experiment_id: str) -> None:
        def work() -> None:
            with RUN_ONE_AT_A_TIME:
                own_experiments, own_preregs = worker_stores()
                runner.run(experiment_id, own_experiments, own_preregs, load_pack, parts=parts)
        threading.Thread(target=work, daemon=True, name=f"lab-{experiment_id[:8]}").start()

    @app.get("/options")
    def options(x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        by_paper = {kind.paper: conditions_of(kind) for kind in kinds.KINDS.values()}
        return {"conditions": by_paper["policies"], "conditionsByPaper": by_paper,
                "models": [{"id": m, "inUsdPerMillion": p[0], "outUsdPerMillion": p[1]} for m, p in runner.PRICES.items()], "maxBudgetUsd": MAX_BUDGET_USD}

    @app.post("/experiments", status_code=201)
    def create(body: CreateBody, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        pack, locked = packs().get(body.pack_id), preregs().get(body.prereg_id)
        found = problems_with(body, pack, locked)
        if found:
            raise HTTPException(422, {"error": "experiment_not_ready", "problems": found})
        config = {"conditions": body.conditions, "seeds": body.seeds, "trials": body.trials, "model": body.model, **config_of(pack.kind)}
        experiment = Experiment(id=str(uuid.uuid4()), paper=body.paper, pack_id=pack.id, prereg_id=locked.id, source="lab", conditions=body.conditions, seeds=body.seeds,
                                trials=body.trials, models={"answer": body.model}, budget_usd=body.budget_usd, git_commit=git_commit(), status="estimated",
                                config_sha256=hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest())
        estimate = runner.estimate(experiment, load_pack(pack.id))
        return experiments().create(experiment.model_copy(update={"notes": {"estimate": estimate, "created_by": x_persona}})).ui()

    @app.get("/experiments")
    def recent(x_persona: str = Header(default="")) -> list[dict]:
        check(x_persona)
        return [e.ui() for e in experiments().recent()]

    @app.get("/experiments/{experiment_id}")
    def one(experiment_id: str, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        return found_experiment(experiments(), experiment_id).ui()

    @app.post("/experiments/{experiment_id}/start", status_code=202)
    def start(experiment_id: str, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        experiment = found_experiment(experiments(), experiment_id)
        if experiment.status in TERMINAL - {"failed"}:
            raise HTTPException(409, f"already_{experiment.status}")
        start_worker(experiment_id)
        return {"started": True}

    @app.get("/experiments/{experiment_id}/progress")
    def progress(experiment_id: str, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        return progress_of(experiments(), found_experiment(experiments(), experiment_id))

    @app.get("/experiments/{experiment_id}/stream")
    async def stream(experiment_id: str) -> StreamingResponse:
        found_experiment(experiments(), experiment_id)  # EventSource cannot send headers; the id is the capability, as with the HQ stream

        async def events():
            while True:
                state = progress_of(experiments(), experiments().get(experiment_id))
                yield f"data: {json.dumps(state)}\n\n"
                if state["status"] in TERMINAL:
                    return
                await asyncio.sleep(STREAM_SECONDS)

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/experiments/{experiment_id}/results")
    def read_results(experiment_id: str, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        experiment = found_experiment(experiments(), experiment_id)
        values, judged = experiments().results_of(experiment_id)
        locked = preregs().get(experiment.prereg_id)
        return {"experiment": experiment.ui(), "metrics": results.snapshot_metrics(values), "verdicts": results.snapshot_verdicts(locked.hypotheses if locked else [], judged),
                "hypotheses": [h.ui() for h in (locked.hypotheses if locked else [])], "preregSha256": locked.sha256 if locked else None,
                "conditions": {c: v["label"] for c, v in kinds.KINDS[KIND_FOR_PAPER.get(experiment.paper, "freshness")].conditions.items()}}

    @app.get("/experiments/{experiment_id}/cases")
    def cases(experiment_id: str, condition: str | None = None, failed: bool = False, offset: int = 0, limit: int = 1, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        found_experiment(experiments(), experiment_id)
        chosen = [c for c in experiments().cases_of(experiment_id) if (condition is None or c.condition == condition) and not (failed and c.passed)]
        return {"total": len(chosen), "offset": offset, "items": [c.ui() for c in chosen[offset:offset + max(1, min(limit, 50))]]}


def conditions_of(kind) -> list[dict]:
    return ([{"code": c, "label": v["label"], "available": True} for c, v in kind.conditions.items()]
            + [{"code": c, "label": kind.unavailable_labels.get(c, c), "available": False, "reason": why} for c, why in kind.unavailable.items()])


def config_of(kind: str) -> dict:
    """What fixes the run beyond its grid, hashed into config_sha256: the answer prompt, or the rules prompt-only writes in."""
    if kind == "security":
        return {"rules_prompt": security_lab.RULES, "conditions_meaning": {c: {k: v for k, v in rules.items() if k != "label"} for c, rules in security_lab.CONDITIONS.items()}}
    return {"prompt": freshness_lab.ANSWER_PROMPT, "top_k": freshness_lab.TOP_K}


def found_experiment(store, experiment_id: str) -> Experiment:
    experiment = store.get(experiment_id)
    if experiment is None:
        raise HTTPException(404, "experiment_not_found")
    return experiment


def progress_of(store, experiment: Experiment) -> dict:
    done = store.count_of(experiment.id)
    return {"status": experiment.status, "stalled": store.stalled(experiment.id, experiment_store.utc_now()), "done": done, "total": experiment.notes.get("estimate", {}).get("cases", 0),
            "costUsd": round(store.cost_of(experiment.id) + experiment.notes.get("lab_usd", 0.0), 4), "budgetUsd": experiment.budget_usd,
            "error": experiment.notes.get("error")}
