# research_conformance.py: a research tool, kept apart from the app. Scores a skill's process models against event logs
# with pm4py (alignment-based fitness and precision). pm4py is AGPL v3, so it never enters the backend: this script runs in
# its own environment, reads files the Lab writes (a model as a pm4py process tree, XES logs) and writes the scores as JSON.
# Nothing in app/ imports it.
#   uv run --no-project --managed-python --python 3.12 --with pm4py python -I backend/scripts/research_conformance.py \
#       --model normative_model.ptree --train train_log.xes --heldout heldout_log.xes [--runs runs.xes] --out scores.json
# Scores: the written procedure (normative) and a model mined from the training log (inductive miner) on the held-out log,
# and, given the Lab's own runs, the procedure on what the agent really did.
import argparse
import json
import warnings

import pm4py

warnings.filterwarnings("ignore")  # pm4py's deprecation chatter is not a result


def scores(model, log) -> dict:
    net, initial, final = pm4py.convert_to_petri_net(model)
    fitness = pm4py.fitness_alignments(log, net, initial, final)
    return {"fitness": round(fitness["log_fitness"], 4), "fitting_traces": round(fitness["percFitTraces"] / 100, 4),
            "precision": round(pm4py.precision_alignments(log, net, initial, final), 4), "traces": len(set(log["case:concept:name"]))}


def main() -> dict:
    parser = argparse.ArgumentParser()
    for name in ("--model", "--train", "--heldout", "--out"):
        parser.add_argument(name, required=True)
    parser.add_argument("--runs")
    args = parser.parse_args()
    normative = pm4py.parse_process_tree(open(args.model).read().strip())
    train, heldout = pm4py.read_xes(args.train), pm4py.read_xes(args.heldout)
    extracted = pm4py.discover_process_tree_inductive(train)
    found = {"pm4py": pm4py.__version__, "normative_on_heldout": scores(normative, heldout), "extracted_on_heldout": scores(extracted, heldout),
             "extracted_model": str(extracted)}
    found["doc_vs_behaviour_delta"] = round(found["extracted_on_heldout"]["fitness"] - found["normative_on_heldout"]["fitness"], 4)
    if args.runs:
        found["normative_on_runs"] = scores(normative, pm4py.read_xes(args.runs))
    open(args.out, "w").write(json.dumps(found, indent=1))
    return found


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
