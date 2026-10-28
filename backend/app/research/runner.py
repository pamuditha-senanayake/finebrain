# runner.py: runs one Lab experiment end to end, whatever its pack's kind (research/kinds.py). Claim it, check its locked
# preregistration still holds, then per condition build its labs, and for every seed, trial and case not yet done: run it,
# store it. Every model call adds to the cost; at the cap the run stops cleanly as budget_reached with what it has.
# Results and gates follow, then teardown. A crash leaves stored cases; starting again resumes after the last one.
# Conditions of a kind that allows it run in parallel threads; the spend is shared under one lock, so the cap still holds.
# Used by: research/experiment_routes.py, tests. Uses: research/kinds.py, research/results.py, research/prereg.py, research/lab_tenant.py.
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.research import kinds, lab_tenant, prereg, results
from app.research.contracts import Experiment
from app.research.experiment_store import utc_now

# Config
PRICES, cost, make_answerer = kinds.PRICES, kinds.cost, kinds.make_answerer  # read here by the routes and older callers
HEARTBEAT_EVERY = 1  # every case: a model call can hang to its 60 s timeout twice, which must not look like a dead worker


class BudgetReached(Exception):
    """The next call would pass the confirmed cap."""


class Stopped(Exception):
    """Another condition's thread stopped the run (the cap, or an error), so this one stops too."""


def kind_of(pack: dict):
    return kinds.KINDS[pack["manifest"].kind]


# --- Before a run

def plan(experiment: Experiment, pack: dict) -> list[tuple[str, int, int, object]]:
    return [(c, seed, trial, item) for c in experiment.conditions for seed in experiment.seeds for trial in range(1, experiment.trials + 1)
            for _, items in kind_of(pack).groups(pack) for item in items]


def estimate(experiment: Experiment, pack: dict) -> dict:
    """What the run will cost before it starts, so a person confirms a cap they understand."""
    kind, cases = kind_of(pack), plan(experiment, pack)
    usd = sum(kind.case_cost(experiment, item) for _, _, _, item in cases) + kind.extra_usd(experiment, pack)
    return {"cases": len(cases), "usd": round(usd, 4)}


# --- The run

def run(experiment_id: str, experiments, preregs, load_pack, answer=None, parts: frozenset[str] = lab_tenant.LAB_PARTS, worker: str | None = None) -> str:
    """Runs or resumes the experiment. `answer` replaces the real models in tests (an answerer for freshness, a dict of models
    for security). Returns its final status ("not_claimed" when another worker holds it)."""
    worker = worker or f"worker_{uuid.uuid4().hex[:8]}"
    if not experiments.claim(experiment_id, worker, utc_now()):
        return "not_claimed"
    experiment = experiments.get(experiment_id)
    if "error" in experiment.notes:  # a resumed run starts without the last stop's error
        experiment = experiments.update(experiment_id, notes={k: v for k, v in experiment.notes.items() if k != "error"})
    try:
        return run_claimed(experiment, experiments, preregs, load_pack(experiment.pack_id), answer, parts, worker)
    except Exception as error:  # the run stops, says why, and can be started again from where it was
        experiments.update(experiment_id, status="failed", notes={**experiments.get(experiment_id).notes, "error": f"{type(error).__name__}: {error}"[:500]})
        return "failed"


def run_claimed(experiment: Experiment, experiments, preregs, pack: dict, answer, parts: frozenset[str], worker: str) -> str:
    # Step 1: the thresholds are the ones that were locked
    locked = preregs.get(experiment.prereg_id)
    if locked is None or not locked.locked_at or not prereg.holds(locked):
        experiments.update(experiment.id, status="failed", notes={**experiment.notes, "error": "preregistration_not_locked_or_changed"})
        return "failed"

    # Step 2: every condition's labs, then every case not yet stored, within the cap
    kind, spent, lock = kind_of(pack), {"usd": experiments.cost_of(experiment.id) + experiment.notes.get("lab_usd", 0.0)}, threading.Lock()
    try:
        reports = run_conditions(experiment, experiments, pack, kind, answer, parts, worker, spent, lock)
    except BudgetReached:
        experiments.update(experiment.id, status="budget_reached", cost_usd=spent["usd"], notes={**experiments.get(experiment.id).notes, "lab_usd": spent["usd"] - experiments.cost_of(experiment.id)})
        return "budget_reached"

    # Step 3: every answer graded by today's rule, then results, gates, verdicts; then the labs go
    if kind.kind == "freshness":
        regrade(experiments, experiment.id, kind.grader(pack))
    return finish(experiment, experiments, locked, reports, spent["usd"], parts, kind)


def run_conditions(experiment: Experiment, experiments, pack: dict, kind, answer, parts, worker: str, spent: dict, lock) -> dict:
    """Each condition in its own thread (one at a time for a kind that says so). The first error stops them all."""
    done, stop = {(c.condition, c.seed, c.trial, c.case_id) for c in experiments.cases_of(experiment.id)}, threading.Event()

    def guarded(condition: str) -> dict:
        try:
            return run_condition(experiment, experiments, pack, kind, condition, answer, parts, worker, spent, lock, done, stop)
        except Exception:
            stop.set()
            raise

    with ThreadPoolExecutor(max_workers=kind.threads, thread_name_prefix="lab-condition") as pool:
        futures = {c: pool.submit(guarded, c) for c in experiment.conditions}
    errors = [f.exception() for f in futures.values() if f.exception()]
    real = [e for e in errors if not isinstance(e, (BudgetReached, Stopped))]
    if real or errors:
        raise (real or errors)[0]
    return {c: f.result() for c, f in futures.items()}


def run_condition(experiment: Experiment, experiments, pack: dict, kind, condition: str, answer, parts, worker: str, spent: dict, lock, done: set, stop) -> dict:
    local = {"usd": 0.0}

    def meter(model: str, tokens_in: int, tokens_out: int) -> None:  # the pipeline's own model calls count against the cap too
        with lock:
            spent["usd"] += cost(model, tokens_in, tokens_out)
            local["usd"] += cost(model, tokens_in, tokens_out)

    def beat() -> None:  # a long build or run is not a dead worker
        experiments.heartbeat(experiment.id, worker, utc_now())

    doubles, gold, reports = kind.doubles(experiment, answer, meter), kind.gold_of(pack), {}
    for group, items in kind.groups(pack):
        lane, reports[group] = kind.build(experiment, condition, group, pack, parts, meter, beat, doubles)
        try:
            for count, (seed, trial, item) in enumerate((s, t, i) for s in experiment.seeds for t in range(1, experiment.trials + 1) for i in items):
                if (condition, seed, trial, kind.case_id(item)) in done:
                    continue
                with lock:
                    if stop.is_set():
                        raise Stopped()
                    if spent["usd"] + kind.case_cost(experiment, item) > experiment.budget_usd:
                        stop.set()
                        raise BudgetReached()
                before = local["usd"]
                case = kind.run_case(experiment, lane, condition, seed, trial, item, gold.get(kind.case_id(item)), pack, doubles)
                case = case.model_copy(update={"cost_usd": local["usd"] - before}) if kind.metered else case
                if experiments.add_case(case) and not kind.metered:
                    with lock:
                        spent["usd"] += case.cost_usd
                if count % HEARTBEAT_EVERY == 0:
                    beat()
            reports[group] = {**reports[group], **kind.finish_lab(lane)}
        finally:
            lab_tenant.close_lab(lane)
    return reports if kind.kind == "security" else reports["all"]  # freshness and skills build one lab per condition


def regrade(experiments, experiment_id: str, grade) -> int:
    """Grade every stored answer again with the current grader (`grade(case_id, answer)` gives the label and the grader's
    version), so one rule judges the whole run, however often it resumed. Answers never change; only labels can.
    Returns how many labels changed."""
    changed = 0
    for case in experiments.cases_of(experiment_id):
        label, version = grade(case.case_id, case.outcome["answer"])
        if label != case.outcome["label"] or case.outcome.get("grader") != version:
            experiments.relabel(case.model_copy(update={"outcome": {**case.outcome, "label": label, "grader": version}, "passed": label == "fresh"}))
            changed += label != case.outcome["label"]
    return changed


def finish(experiment: Experiment, experiments, locked, reports: dict, spent: float, parts: frozenset[str], kind) -> str:
    cases = experiments.cases_of(experiment.id)
    values = results.metric_values(experiment.id, cases, experiment.conditions, kind.kind)
    checked = results.gates(values, experiment.conditions, kind.kind, reports, cases)
    judged = results.comparisons(locked.hypotheses, cases, experiment.id, checked["passed"])
    experiments.save_results(experiment.id, values, judged)
    torn = {lab: lab_tenant.teardown(lab)["complete"] for lab in kind.lab_ids(experiment.id, experiment.conditions)} if parts else {}
    status = "finished" if checked["passed"] else "invalid_run"
    experiments.update(experiment.id, status=status, finished_at=utc_now().isoformat(), cost_usd=spent,
                       notes={**experiments.get(experiment.id).notes, "ingest": reports, "gates": checked, "teardown": torn})
    return status
