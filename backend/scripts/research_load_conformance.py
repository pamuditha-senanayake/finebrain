# research_load_conformance.py: a dev script. Adds the conformance scores (scripts/research_conformance.py, run apart with
# pm4py) to a skills experiment's results, beside its task success and pass^k:
#   uv run python scripts/research_load_conformance.py <experiment id> B0=<scores_B0.json> B1=<scores_B1.json>
# Per condition: the written procedure's fitness and precision on the agent's own runs; and, from the pack's logs (the same
# in every condition), fitness and precision on the held-out log and the documented-versus-observed gap.
# Uses: research/experiment_store.py, research/contracts.py.
import json
import sys

from app.research import experiment_store, store
from app.research.contracts import MetricValue


def rows(experiment_id: str, condition: str, scores: dict) -> list[MetricValue]:
    found = {"fitness_runs": scores["normative_on_runs"]["fitness"], "precision_runs": scores["normative_on_runs"]["precision"],
             "fitness_heldout": scores["normative_on_heldout"]["fitness"], "precision_heldout": scores["normative_on_heldout"]["precision"],
             "doc_vs_behaviour_delta": scores["doc_vs_behaviour_delta"]}
    traces = {"fitness_runs": scores["normative_on_runs"]["traces"], "precision_runs": scores["normative_on_runs"]["traces"]}
    return [MetricValue(experiment_id=experiment_id, metric_key=key, condition=condition, value=value, unit="ratio", n=traces.get(key, scores["normative_on_heldout"]["traces"]),
                        ci_low=value, ci_high=value, ci_level=0.95, provenance="lab") for key, value in found.items()]


if __name__ == "__main__":
    experiment_id, experiments = sys.argv[1], experiment_store.PostgresExperiments(store.connect())
    values, judged = experiments.results_of(experiment_id)
    new = [row for arg in sys.argv[2:] for row in rows(experiment_id, arg.split("=")[0], json.loads(open(arg.split("=", 1)[1]).read()))]
    keys = {(v.metric_key, v.condition) for v in new}
    experiments.save_results(experiment_id, [v for v in values if (v.metric_key, v.condition) not in keys] + new, judged)
    print(len(new), "conformance values added")
