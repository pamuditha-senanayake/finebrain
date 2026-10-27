# results.py: from case results to what the paper reports. Each freshness metric is a share of graded cases with its Wilson
# interval; each preregistered hypothesis gets its effect, interval, test and verdict; the gates decide whether the run can
# be read at all (spec section 4.4): every canary right in every condition, retrieval reaching the evidence (Execution_V1's
# frozen 0.60), and a baseline that is not degenerate. A failed gate makes every verdict invalid_run.
# Used by: research/runner.py, research/experiment_routes.py. Uses: research/stats.py, research/contracts.py.
from app.research import stats
from app.research.contracts import CaseResult, Comparison, Hypothesis, MetricValue, ResearchMetric, ResearchVerdict

# Config
METRICS = {  # key: (label, query kind it counts, labels that count as a hit, definition)
    "stale_answer_rate": ("Stale answers", "stale_sensitive", {"stale"}, "Answers stating a superseded value, over questions whose fact changed."),
    "as_of_now_current": ("Current answers", "stale_sensitive", {"fresh"}, "Answers stating the value valid at the question's date, over questions whose fact changed."),
    "mixed_rate": ("Mixed answers", "stale_sensitive", {"mixed"}, "Answers stating both the old and the new value."),
    "refusal_rate": ("Refusals", "stale_sensitive", {"refused"}, "Answers saying the context does not hold the answer."),
    "control_accuracy": ("Control accuracy", "control", {"fresh"}, "Correct answers to questions about facts that never changed."),
    "canary_accuracy": ("Canary accuracy", "canary", {"fresh"}, "Correct answers to the canary questions; anything below 100% is a pipeline defect."),
    "retrieval_either_recall": ("Evidence reached", "stale_sensitive", None, "Questions whose old or new sentence was in what S5 gave the answerer."),
}
MIN_EITHER_RECALL = 0.60  # Execution_V1 frozen_config retrieval gate
MIN_BASELINE_CONTROL = 0.5  # below this the baseline answers nothing right and every comparison against it is empty


def hit(case: CaseResult, metric: str) -> bool | None:
    """Whether this case counts for the metric; None when the metric does not look at this kind of question."""
    _, kind, labels, _ = METRICS[metric]
    if case.outcome.get("kind") != kind:
        return None
    return bool(case.outcome.get("either_hit")) if labels is None else case.outcome.get("label") in labels


def hits_by(cases: list[CaseResult], metric: str, condition: str) -> dict[str, list[float]]:
    """Per question, its outcomes across seeds and trials, as 1 or 0."""
    found: dict[str, list[float]] = {}
    for case in cases:
        counted = hit(case, metric) if case.condition == condition else None
        if counted is not None:
            found.setdefault(case.case_id, []).append(1.0 if counted else 0.0)
    return found


def metric_values(experiment_id: str, cases: list[CaseResult], conditions: list[str]) -> list[MetricValue]:
    values = []
    for metric in METRICS:
        for condition in conditions:
            outcomes = [o for found in hits_by(cases, metric, condition).values() for o in found]
            low, high = stats.wilson(int(sum(outcomes)), len(outcomes))
            values.append(MetricValue(experiment_id=experiment_id, metric_key=metric, condition=condition, value=sum(outcomes) / len(outcomes) if outcomes else 0.0,
                                      unit="ratio", n=len(outcomes), ci_low=low, ci_high=high, ci_level=stats.LEVEL, provenance="lab"))
    return values


# --- Hypotheses

def clears(value: float, comparator: str, threshold: float) -> bool:
    return {"at_least": value >= threshold, "at_most": value <= threshold, "below": value < threshold, "above": value > threshold}[comparator]


def compare(h: Hypothesis, cases: list[CaseResult], experiment_id: str) -> Comparison:
    """Two conditions: the effect a minus b, with a paired test. One: the value itself, judged by its interval's far end."""
    first = hits_by(cases, h.metric, h.conditions[0])
    if len(h.conditions) == 1:
        outcomes = [o for found in first.values() for o in found]
        value, (low, high) = (sum(outcomes) / len(outcomes) if outcomes else 0.0), stats.wilson(int(sum(outcomes)), len(outcomes))
        if h.test == "rule_of_three" and not sum(outcomes):
            high = stats.rule_of_three(len(outcomes))
        far = low if h.comparator in ("at_least", "above") else high  # the interval must clear the threshold, not only the point
        verdict = "supported" if outcomes and clears(far, h.comparator, h.threshold) else "not_supported"
        return Comparison(experiment_id=experiment_id, hypothesis_id=h.id, metric_key=h.metric, condition_a=h.conditions[0], condition_b="", effect=value,
                          ci_low=low, ci_high=high, test=h.test, verdict=verdict, diagnosis_stage=None if verdict == "supported" else h.diagnosis_stage)
    second = hits_by(cases, h.metric, h.conditions[1])
    paired = stats.paired_bootstrap(first, second)
    flat_a = {f"{q}:{i}": bool(v) for q, found in first.items() for i, v in enumerate(found)}
    flat_b = {f"{q}:{i}": bool(v) for q, found in second.items() for i, v in enumerate(found)}
    test = stats.mcnemar_exact(*stats.discordant(flat_a, flat_b)) if h.test == "exact_mcnemar" else {"statistic": None, "p": paired["p"]}
    verdict = "supported" if paired["n"] and clears(paired["effect"], h.comparator, h.threshold) and test["p"] < h.alpha else "not_supported"
    return Comparison(experiment_id=experiment_id, hypothesis_id=h.id, metric_key=h.metric, condition_a=h.conditions[0], condition_b=h.conditions[1],
                      effect=paired["effect"], ci_low=paired["low"], ci_high=paired["high"], test=h.test, statistic=test["statistic"], p_value=test["p"],
                      verdict=verdict, diagnosis_stage=None if verdict == "supported" else h.diagnosis_stage)


def comparisons(hypotheses: list[Hypothesis], cases: list[CaseResult], experiment_id: str, valid: bool) -> list[Comparison]:
    """Every hypothesis judged; Holm-adjusted p reported beside the raw one (primaries are judged on the raw p, as preregistered)."""
    judged = [compare(h, cases, experiment_id) for h in hypotheses]
    adjusted = stats.holm({c.hypothesis_id: c.p_value for c in judged if c.p_value is not None})
    return [c.model_copy(update={"p_adjusted": adjusted.get(c.hypothesis_id), **({} if valid else {"verdict": "invalid_run"})}) for c in judged]


# --- Gates

def gates(values: list[MetricValue], conditions: list[str]) -> dict:
    by = {(v.metric_key, v.condition): v for v in values}
    baseline = conditions[0]
    checks = {
        "canaries": all(by[("canary_accuracy", c)].n and by[("canary_accuracy", c)].value == 1.0 for c in conditions),
        "retrieval": by[("retrieval_either_recall", baseline)].value >= MIN_EITHER_RECALL,
        "baseline": not_degenerate(by, baseline),
    }
    return {"passed": all(checks.values()), "checks": checks, "baseline": baseline}


def not_degenerate(by: dict, baseline: str) -> bool:
    """Control questions right at least half the time; a pack without controls: the baseline answers at least half."""
    controls = by[("control_accuracy", baseline)]
    if controls.n:
        return controls.value >= MIN_BASELINE_CONTROL
    return by[("refusal_rate", baseline)].value <= 1 - MIN_BASELINE_CONTROL


# --- For the console

def snapshot_metrics(values: list[MetricValue]) -> list[dict]:
    return [ResearchMetric(key=v.metric_key, label=METRICS[v.metric_key][0], definition=METRICS[v.metric_key][3], value=v.value, unit="ratio",
                           condition=v.condition, series=[], provenance=v.provenance, n=v.n, ci={"low": v.ci_low, "high": v.ci_high, "level": v.ci_level},
                           experiment_id=v.experiment_id).ui() for v in values]


def snapshot_verdicts(hypotheses: list[Hypothesis], judged: list[Comparison]) -> list[dict]:
    words = {h.id: h for h in hypotheses}
    return [ResearchVerdict(hypothesis_id=c.hypothesis_id, metric_key=c.metric_key, test=c.test, verdict=c.verdict, diagnosis_stage=c.diagnosis_stage,
                            threshold=f"{words[c.hypothesis_id].comparator.replace('_', ' ')} {words[c.hypothesis_id].threshold:+.2f}" if c.hypothesis_id in words else "",
                            observed=f"{c.effect:+.3f} [{c.ci_low:+.3f}, {c.ci_high:+.3f}]" + (f", p {c.p_value:.4f}" if c.p_value is not None else ""),
                            p_adjusted=c.p_adjusted).ui() for c in judged]
