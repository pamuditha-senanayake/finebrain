# runner.py: runs one freshness experiment end to end. Claim it, check its locked preregistration still holds, then per
# condition build the lab, and for every seed, trial and question not yet done: ask, grade, store. Every model call adds to
# the cost; at the cap the run stops cleanly as budget_reached with what it has. Results and gates follow, then teardown.
# A crash leaves stored cases; starting again resumes after the last one. Used by: research/experiment_routes.py, tests.
# Uses: research/freshness_lab.py, research/grade_freshness.py, research/results.py, research/prereg.py, research/lab_tenant.py, llm.py.
import time
import uuid

import anthropic

from app.pipeline import llm
from app.pipeline.retry import call_with_retry
from app.research import freshness_lab, grade_freshness, lab_tenant, prereg, results
from app.research.contracts import CaseResult, Experiment
from app.research.experiment_store import utc_now

# Config
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}  # USD per million tokens, in and out
ANSWER_MAX_TOKENS = 300
EXPECTED_IN, EXPECTED_OUT = 1_800, 60  # one question: eight chunks plus the prompt, and a one or two sentence answer
LIVING_MAP_PER_DOCUMENT = 0.002  # one Haiku extraction window per short document
LIVING_MAP_PER_FACT = 0.03  # one Opus conflict proposal per changed fact
HEARTBEAT_EVERY = 10  # cases


class BudgetReached(Exception):
    """The next call would pass the confirmed cap."""


def cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES[model]
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


# --- Before a run

def plan(experiment: Experiment, pack: dict) -> list[tuple[str, int, int, object]]:
    return [(c, seed, trial, q) for c in experiment.conditions for seed in experiment.seeds for trial in range(1, experiment.trials + 1) for q in pack["main"]]


def estimate(experiment: Experiment, pack: dict) -> dict:
    """What the run will cost before it starts, so a person confirms a cap they understand."""
    cases = len(plan(experiment, pack))
    model = experiment.models["answer"]
    asking = cases * cost(model, EXPECTED_IN, EXPECTED_OUT)
    living = "C3" in experiment.conditions
    lane_b = (len(pack["documents"]) * LIVING_MAP_PER_DOCUMENT + len(pack["extra"].get("facts.jsonl", [])) * LIVING_MAP_PER_FACT) if living else 0.0
    return {"cases": cases, "tokens_in": cases * EXPECTED_IN, "tokens_out": cases * EXPECTED_OUT, "usd": round(asking + lane_b, 4)}


def make_answerer(model: str, client=None):
    """One answer from Claude, with its usage. Haiku answers without thinking; the larger models think at low effort."""
    client = client or anthropic.Anthropic(timeout=llm.REASON_TIMEOUT_SECONDS, max_retries=0)
    thinking = {"thinking": {"type": "disabled"}} if "haiku" in model else {}

    def answer(prompt: str) -> tuple[str, dict]:
        reply = call_with_retry(lambda: client.messages.create(model=model, max_tokens=ANSWER_MAX_TOKENS, output_config={"effort": "low"}, **thinking,
                                                               messages=[{"role": "user", "content": prompt}]), llm.is_retryable, attempts=llm.ATTEMPTS)
        return llm.first_text(reply), {"in": reply.usage.input_tokens, "out": reply.usage.output_tokens}

    return answer


# --- One case

def run_case(experiment: Experiment, lane, condition: str, seed: int, trial: int, query, gold, facts: dict, answer) -> CaseResult:
    started = time.monotonic()
    asked = freshness_lab.ask(lane, query.text, query.as_of, answer)
    label = grade_freshness.grade(asked["answer"], gold.expected_value, gold.superseded_values, gold.tolerance)
    fact = facts.get(query.fact_id)
    sentences = [s for s in ((fact.old_sentence, fact.new_sentence) if fact else ()) if s]
    outcome = {"kind": query.kind, "label": label, "answer": asked["answer"], "expected": gold.expected_value, "superseded": gold.superseded_values,
               "items": asked["items"], "either_hit": any(s in asked["context"] for s in sentences), "as_of": query.as_of}
    model = experiment.models["answer"]
    return CaseResult(experiment_id=experiment.id, condition=condition, seed=seed, trial=trial, case_id=query.query_id, outcome=outcome,
                      passed=label == "fresh", latency_ms=int((time.monotonic() - started) * 1000), tokens_in=asked["usage"]["in"],
                      tokens_out=asked["usage"]["out"], cost_usd=cost(model, asked["usage"]["in"], asked["usage"]["out"]))


# --- The run

def run(experiment_id: str, experiments, preregs, load_pack, answer=None, parts: frozenset[str] = lab_tenant.LAB_PARTS, worker: str | None = None) -> str:
    """Runs or resumes the experiment. Returns its final status ("not_claimed" when another worker holds it)."""
    worker = worker or f"worker_{uuid.uuid4().hex[:8]}"
    if not experiments.claim(experiment_id, worker, utc_now()):
        return "not_claimed"
    experiment = experiments.get(experiment_id)
    try:
        return run_claimed(experiment, experiments, preregs, load_pack(experiment.pack_id), answer or make_answerer(experiment.models["answer"]), parts, worker)
    except Exception as error:  # the run stops, says why, and can be started again from where it was
        experiments.update(experiment_id, status="failed", notes={**experiments.get(experiment_id).notes, "error": f"{type(error).__name__}: {error}"[:500]})
        return "failed"


def run_claimed(experiment: Experiment, experiments, preregs, pack: dict, answer, parts: frozenset[str], worker: str) -> str:
    # Step 1: the thresholds are the ones that were locked
    locked = preregs.get(experiment.prereg_id)
    if locked is None or not locked.locked_at or not prereg.holds(locked):
        experiments.update(experiment.id, status="failed", notes={**experiment.notes, "error": "preregistration_not_locked_or_changed"})
        return "failed"

    # Step 2: every condition's lab, then every case not yet stored, within the cap
    spent = {"usd": experiments.cost_of(experiment.id) + experiment.notes.get("lab_usd", 0.0)}

    def meter(model: str, tokens_in: int, tokens_out: int) -> None:  # Lane B's model calls count against the cap too
        spent["usd"] += cost(model, tokens_in, tokens_out)

    try:
        reports = ask_everything(experiment, experiments, pack, answer, parts, worker, spent, meter)
    except BudgetReached:
        experiments.update(experiment.id, status="budget_reached", cost_usd=spent["usd"], notes={**experiments.get(experiment.id).notes, "lab_usd": spent["usd"] - experiments.cost_of(experiment.id)})
        return "budget_reached"

    # Step 3: results, gates, verdicts; then the labs go
    return finish(experiment, experiments, locked, reports, spent["usd"], parts)


def ask_everything(experiment: Experiment, experiments, pack: dict, answer, parts, worker: str, spent: dict, meter) -> dict:
    gold, facts = {g.query_id: g for g in pack["gold"]}, {f.fact_id: f for f in pack["extra"].get("facts.jsonl", [])}
    done = {(c.condition, c.seed, c.trial, c.case_id) for c in experiments.cases_of(experiment.id)}
    reports = {}
    for condition in experiment.conditions:
        lane, reports[condition] = freshness_lab.build(experiment.id, condition, pack, parts, meter)
        for count, (_, seed, trial, query) in enumerate(item for item in plan(experiment, pack) if item[0] == condition):
            if (condition, seed, trial, query.query_id) in done:
                continue
            if spent["usd"] + cost(experiment.models["answer"], EXPECTED_IN, EXPECTED_OUT) > experiment.budget_usd:
                raise BudgetReached()
            case = run_case(experiment, lane, condition, seed, trial, query, gold[query.query_id], facts, answer)
            if experiments.add_case(case):
                spent["usd"] += case.cost_usd
            if count % HEARTBEAT_EVERY == 0:
                experiments.heartbeat(experiment.id, worker, utc_now())
        lab_tenant.close_lab(lane)
    return reports


def finish(experiment: Experiment, experiments, locked, reports: dict, spent: float, parts: frozenset[str]) -> str:
    cases = experiments.cases_of(experiment.id)
    values = results.metric_values(experiment.id, cases, experiment.conditions)
    checked = results.gates(values, experiment.conditions)
    judged = results.comparisons(locked.hypotheses, cases, experiment.id, checked["passed"])
    experiments.save_results(experiment.id, values, judged)
    torn = {c: lab_tenant.teardown(freshness_lab.lab_id_for(experiment.id, c))["complete"] for c in experiment.conditions} if parts else {}
    status = "finished" if checked["passed"] else "invalid_run"
    experiments.update(experiment.id, status=status, finished_at=utc_now().isoformat(), cost_usd=spent,
                       notes={**experiments.get(experiment.id).notes, "ingest": reports, "gates": checked, "teardown": torn})
    return status
