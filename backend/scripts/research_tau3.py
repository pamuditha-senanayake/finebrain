# research_tau3.py: a dev script. The tau3-bench adapter (sierra-research/tau2-bench, package tau2 2.0 or later, Python 3.12,
# MIT): tau runs in its own environment outside the repo, and this script, which imports nothing from tau or the app, turns
# its results into pass^1 to pass^n with bootstrap intervals over tasks, and the run's cost from its token counts.
#   1. In a tau2-bench checkout:  uv sync --managed-python
#   2. .venv/bin/tau2 run --domain retail --communicate-scorer substring --agent-llm anthropic/claude-haiku-5-5 --agent-llm-args '{}' \
#        --user-llm anthropic/claude-haiku-5-5 --user-llm-args '{}' --num-trials 8 --task-ids <ids> --save-to <name>
#      (<ids>: the first 30 retail tasks graded without nl_assertions, which tau judges with an OpenAI model it hard-codes;
#      40 of the 114 retail tasks are, so the Lab's set is the deterministically graded ones)
#      ('{}' because tau sends temperature 0 by default, which current Claude models refuse; model defaults also keep
#      the trials of pass^k independent samples, as the spec asks; substring: original tau-bench's deterministic check of what
#      the agent told the customer, where the default asks an OpenAI model to judge it)
#   3. uv run python scripts/research_tau3.py <checkout>/data/simulations/<name>/results.json <out.json>
# tau2 releases before 1.0.1 graded differently, so their results are refused.
import json
import math
import random
import sys

# Config
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}  # USD per million tokens, in and out
KS, RESAMPLES, SEED = (1, 2, 4, 8), 10_000, 42
OLDEST = (1, 0, 1)


def pass_hat_k(c: int, n: int, k: int) -> float:
    return math.comb(c, k) / math.comb(n, k)


def interval(values: list[float]) -> tuple[float, float]:
    rng, n = random.Random(SEED), len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(RESAMPLES))
    return means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES) - 1]


def version_ok(results: dict) -> bool:
    found = str((results.get("info") or {}).get("tau2_version") or (results.get("info") or {}).get("version") or "")
    parts = tuple(int(p) for p in found.split(".")[:3] if p.isdigit())
    return not parts or parts >= OLDEST  # a release that names no version is the current checkout


def summarize(results: dict, model: str) -> dict:
    by_task: dict[str, list[bool]] = {}
    tokens_in = tokens_out = 0
    for sim in results["simulations"]:
        by_task.setdefault(str(sim["task_id"]), []).append((sim.get("reward_info") or {}).get("reward") == 1.0)
        for message in sim.get("messages") or []:
            usage = message.get("usage") or {}
            tokens_in, tokens_out = tokens_in + usage.get("prompt_tokens", 0), tokens_out + usage.get("completion_tokens", 0)
    errored = sum(1 for sim in results["simulations"] if "error" in str(sim.get("termination_reason", "")).lower())
    n = min(len(t) for t in by_task.values())
    complete = {task: sum(found[:n]) for task, found in by_task.items()}
    curve = {}
    for k in (k for k in KS if k <= n):
        values = [pass_hat_k(c, n, k) for c in complete.values()]
        low, high = interval(values)
        curve[f"pass_hat_{k}"] = {"value": sum(values) / len(values), "low": low, "high": high, "tasks": len(values)}
    price_in, price_out = PRICES[model]
    return {"benchmark": "tau3-bench retail", "model": model, "tasks": len(complete), "trials": n, "errored": errored, "curve": curve,
            "cost_usd": round((tokens_in * price_in + tokens_out * price_out) / 1_000_000, 4), "tokens": {"in": tokens_in, "out": tokens_out}}


if __name__ == "__main__":
    results = json.loads(open(sys.argv[1]).read())
    if not version_ok(results):
        sys.exit("tau2 before 1.0.1 graded differently; these results are not comparable")
    found = summarize(results, sys.argv[3] if len(sys.argv) > 3 else "claude-haiku-5-5")
    open(sys.argv[2], "w").write(json.dumps(found, indent=1))
    print(json.dumps(found, indent=1))
