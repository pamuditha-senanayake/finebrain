# kinds.py: what the runner needs from each kind of pack, so one runner runs them all: its conditions, how its cases group
# into labs, how a lab is built, how one case runs, what it should cost, and which labs to tear down. Freshness runs one
# lab per condition, one condition at a time; security runs one lab per condition and episode family, conditions in parallel.
# Used by: research/runner.py, research/experiment_routes.py. Uses: research/freshness_lab.py, research/security_lab.py, research/grade_freshness.py,
# research/grade_nuggets.py, llm.py.
import time

import anthropic

from app.pipeline import llm
from app.pipeline.audit import verify_chain
from app.pipeline.retry import call_with_retry
from app.research import freshness_lab, grade_freshness, grade_nuggets, security_lab
from app.research.contracts import CaseResult, Experiment

# Config
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}  # USD per million tokens, in and out
ANSWER_MAX_TOKENS = 300


def cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES[model]
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def make_answerer(model: str, client=None):
    """One answer from Claude, with its usage. Haiku answers without thinking; the larger models think at low effort."""
    client = client or anthropic.Anthropic(timeout=llm.REASON_TIMEOUT_SECONDS, max_retries=0)
    thinking = {"thinking": {"type": "disabled"}} if "haiku" in model else {}

    def answer(prompt: str) -> tuple[str, dict]:
        reply = call_with_retry(lambda: client.messages.create(model=model, max_tokens=ANSWER_MAX_TOKENS, output_config={"effort": "low"}, **thinking,
                                                               messages=[{"role": "user", "content": prompt}]), llm.is_retryable, attempts=llm.ATTEMPTS)
        return llm.first_text(reply), {"in": reply.usage.input_tokens, "out": reply.usage.output_tokens}

    return answer


class Freshness:
    kind, paper, threads, metered = "freshness", "policies", 1, False  # metered: False when each case reports its own usage
    conditions, unavailable, unavailable_labels = freshness_lab.CONDITIONS, freshness_lab.UNAVAILABLE, {"C2": "Delete and rebuild"}
    expected_in, expected_out = 1_800, 60  # one question: eight chunks plus the prompt, and a one or two sentence answer
    living_per_document, living_per_fact = 0.002, 0.03  # Lane B: one Haiku extraction window per document, one Opus proposal per fact

    def groups(self, pack: dict) -> list[tuple[str, list]]:
        return [("all", pack["main"])]

    def case_id(self, item) -> str:
        return item.query_id

    def gold_of(self, pack: dict) -> dict:
        return {g.query_id: g for g in pack["gold"]}

    def doubles(self, experiment: Experiment, given, meter):
        return given or make_answerer(experiment.models["answer"])

    def build(self, experiment: Experiment, condition: str, group: str, pack: dict, parts, meter, beat, doubles):
        return freshness_lab.build(experiment.id, condition, pack, parts, meter, beat)

    def case_cost(self, experiment: Experiment, item) -> float:
        return cost(experiment.models["answer"], self.expected_in, self.expected_out)

    def run_case(self, experiment: Experiment, lane, condition: str, seed: int, trial: int, query, gold, pack: dict, answer) -> CaseResult:
        started = time.monotonic()
        asked = freshness_lab.ask(lane, query.text, query.as_of, answer, freshness_lab.prompt_of(pack))
        label, version = (pack.get("_grade") or pack.setdefault("_grade", self.grader(pack)))(query.query_id, asked["answer"])  # built once per run
        fact = {f.fact_id: f for f in pack["extra"].get("facts.jsonl", [])}.get(query.fact_id)
        sentences = [s for s in ((fact.old_sentence, fact.new_sentence) if fact else ()) if s]
        outcome = {"kind": query.kind, "question": query.text, "label": label, "grader": version, "answer": asked["answer"], "expected": gold.expected_value,
                   "superseded": gold.superseded_values, "items": asked["items"], "either_hit": any(s in asked["context"] for s in sentences), "as_of": query.as_of}
        usage = asked["usage"]
        return CaseResult(experiment_id=experiment.id, condition=condition, seed=seed, trial=trial, case_id=query.query_id, outcome=outcome, passed=label == "fresh",
                          latency_ms=int((time.monotonic() - started) * 1000), tokens_in=usage["in"], tokens_out=usage["out"],
                          cost_usd=cost(experiment.models["answer"], usage["in"], usage["out"]))

    def grader(self, pack: dict):
        """grade(query_id, answer) -> (label, grader version): by the pack's nuggets when it has them (a stale answer states
        the value of the same article's question at another date), else by the gold value and its superseded ones."""
        nuggets: dict[str, list] = {}
        for nugget in pack["extra"].get("nuggets.jsonl", []):
            nuggets.setdefault(nugget.query_id, []).append(nugget)
        gold, article = self.gold_of(pack), {q.query_id: q.fact_id for q in pack["main"]}
        values = {q: {n.target for n in found if n.kind == "numeric_tol"} for q, found in nuggets.items()}
        others = {q: [nuggets[o] for o in nuggets if o != q and article.get(o) == article.get(q) and values[o] != values[q]] for q in nuggets}

        def grade(query_id: str, answer: str) -> tuple[str, str]:
            if query_id in nuggets:
                return grade_nuggets.grade(answer, nuggets[query_id], others[query_id]), grade_nuggets.GRADER_VERSION
            g = gold[query_id]
            return grade_freshness.grade(answer, g.expected_value, g.superseded_values, g.tolerance), grade_freshness.GRADER_VERSION
        return grade

    def finish_lab(self, lane) -> dict:
        return {}

    def lab_ids(self, experiment_id: str, conditions: list[str]) -> list[str]:
        return [freshness_lab.lab_id_for(experiment_id, c) for c in conditions]

    def extra_usd(self, experiment: Experiment, pack: dict) -> float:
        if "C3" not in experiment.conditions:
            return 0.0
        return len(pack["documents"]) * self.living_per_document + len(pack["extra"].get("facts.jsonl", [])) * self.living_per_fact


class Security:
    kind, paper, threads, metered = "security", "security", 4, True  # every model call goes through the meter
    conditions, unavailable, unavailable_labels = security_lab.CONDITIONS, security_lab.UNAVAILABLE, {}
    act_tokens, read_tokens, grade_tokens = (4_000, 350), (2_600, 200), (2_000, 120)  # S6 with one correction; an Ask answer; the S7 grader

    def groups(self, pack: dict) -> list[tuple[str, list]]:
        return security_lab.groups(pack)

    def case_id(self, item) -> str:
        return item.task_id

    def gold_of(self, pack: dict) -> dict:
        return {g.task_id: g for g in pack["gold"]}

    def doubles(self, experiment: Experiment, given, meter):
        return given or security_lab.real_models(meter, experiment.models["answer"])

    def build(self, experiment: Experiment, condition: str, group: str, pack: dict, parts, meter, beat, doubles):
        return security_lab.build(experiment.id, condition, group, pack, parts, meter, beat, doubles)

    def case_cost(self, experiment: Experiment, task) -> float:
        model = experiment.models["answer"]
        if task.path == "read":
            return cost(model, *self.read_tokens)
        return cost(model, *self.act_tokens) + cost(llm.FAST_MODEL, *self.grade_tokens)

    def run_case(self, experiment: Experiment, lane, condition: str, seed: int, trial: int, task, gold, pack: dict, doubles) -> CaseResult:
        started = time.monotonic()
        outcome = security_lab.run_episode(lane, task, gold, self.conditions[condition]["rules"])
        passed = outcome["label"] != "leak" and outcome["goal_met"] is not False
        return CaseResult(experiment_id=experiment.id, condition=condition, seed=seed, trial=trial, case_id=task.task_id, correlation_id=outcome.get("run_id"),
                          outcome=outcome, passed=passed, latency_ms=int((time.monotonic() - started) * 1000), tokens_in=0, tokens_out=0, cost_usd=0.0)

    def finish_lab(self, lane) -> dict:
        """The lab's audit log must still be one unbroken hash chain after every episode."""
        return {"audit_ok": verify_chain(lane.audit.in_order()) is None}

    def lab_ids(self, experiment_id: str, conditions: list[str]) -> list[str]:
        return [security_lab.lab_id_for(experiment_id, c, group) for c in conditions for group in ("base", "document")]

    def extra_usd(self, experiment: Experiment, pack: dict) -> float:
        return 0.0


KINDS = {"freshness": Freshness(), "security": Security()}
PAPER_FOR_KIND = {name: kind.paper for name, kind in KINDS.items()}
