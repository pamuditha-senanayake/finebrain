# stats.py: every number the Lab shows or exports goes through here (spec section 8). Intervals for one proportion, the
# rule of three, exact McNemar for paired yes/no outcomes, a paired bootstrap at task level with seeds pooled as clusters,
# the unbiased pass^k, Holm's correction, Cohen's kappa and h. Pure Python, seeded, so the same input gives the same answer.
# Used by: research/results.py, tests/test_research_stats.py. Uses: nothing local.
import math
import random
from statistics import NormalDist, mean

# Config
LEVEL = 0.95
RESAMPLES = 10_000
SEED = 20260818  # the frozen config's seed: bootstrap intervals repeat exactly
MIN_SEEDS, MORE_SEEDS = 3, 5


def z_for(level: float) -> float:
    return NormalDist().inv_cdf(1 - (1 - level) / 2)


# --- One proportion

def wilson(successes: int, n: int, level: float = LEVEL) -> tuple[float, float]:
    """Wilson score interval. Unlike the plain normal interval it stays inside 0 to 1 and works near 0 and 1."""
    if n == 0:
        return 0.0, 1.0
    z, p = z_for(level), successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def rule_of_three(n: int) -> float:
    """With zero events in n tries, the 95 percent upper bound on the rate is about 3/n."""
    return 3 / n if n else 1.0


def episodes_for_zero_rate(max_rate: float, level: float = LEVEL) -> int:
    """How many tries with zero events let us claim the rate is below max_rate (300 for 1 percent at 95 percent)."""
    return math.ceil(-math.log(1 - level) / max_rate)


# --- Two conditions on the same items

def mcnemar_exact(only_a: int, only_b: int) -> dict:
    """Exact two-sided McNemar: only the discordant pairs count, each side equally likely under no difference."""
    n = only_a + only_b
    tail = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2 ** n if n else 1.0
    return {"only_a": only_a, "only_b": only_b, "statistic": min(only_a, only_b), "p": min(1.0, 2 * tail)}


def discordant(a: dict[str, bool], b: dict[str, bool]) -> tuple[int, int]:
    """Items true under a only, and under b only, over the items both conditions answered."""
    shared = a.keys() & b.keys()
    return sum(a[k] and not b[k] for k in shared), sum(b[k] and not a[k] for k in shared)


def paired_bootstrap(a: dict[str, list[float]], b: dict[str, list[float]], resamples: int = RESAMPLES, level: float = LEVEL, seed: int = SEED) -> dict:
    """Effect of a minus b, resampling whole tasks so a task's seeds and trials move together (clusters).
    `a` and `b` map a task to its outcomes (one per seed and trial). Returns the effect, its interval and a two-sided p."""
    tasks = sorted(a.keys() & b.keys())
    if not tasks:
        return {"effect": 0.0, "low": 0.0, "high": 0.0, "p": 1.0, "n": 0}
    differences = [mean(a[t]) - mean(b[t]) for t in tasks]
    effects = sorted(resampled_means(differences, resamples, seed))
    low, high = percentile(effects, (1 - level) / 2), percentile(effects, 1 - (1 - level) / 2)
    below, above = sum(e <= 0 for e in effects) / resamples, sum(e >= 0 for e in effects) / resamples
    return {"effect": mean(differences), "low": low, "high": high, "p": min(1.0, 2 * min(below, above)), "n": len(tasks)}


def bootstrap_mean(values: list[float], resamples: int = RESAMPLES, level: float = LEVEL, seed: int = SEED) -> dict:
    """A mean with its percentile bootstrap interval, for fitness, precision or pass^k over tasks."""
    if not values:
        return {"estimate": 0.0, "low": 0.0, "high": 0.0, "n": 0}
    means = sorted(resampled_means(values, resamples, seed))
    return {"estimate": mean(values), "low": percentile(means, (1 - level) / 2), "high": percentile(means, 1 - (1 - level) / 2), "n": len(values)}


def resampled_means(values: list[float], resamples: int, seed: int) -> list[float]:
    rng, n = random.Random(seed), len(values)
    return [sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)]


def percentile(ordered: list[float], q: float) -> float:
    """Linear interpolation between the two nearest ranks."""
    position = q * (len(ordered) - 1)
    below, above = math.floor(position), math.ceil(position)
    return ordered[below] + (ordered[above] - ordered[below]) * (position - below)


# --- pass^k

def pass_hat_k(successes: int, trials: int, k: int) -> float:
    """The unbiased chance that k trials drawn from the n run all pass: C(c, k) / C(n, k)."""
    if k > trials:
        raise ValueError("k cannot exceed the number of trials")
    return math.comb(successes, k) / math.comb(trials, k)


def pass_hat_k_over_tasks(successes_by_task: dict[str, int], trials: int, k: int) -> dict:
    return bootstrap_mean([pass_hat_k(c, trials, k) for c in successes_by_task.values()])


# --- Many tests, agreement and effect sizes

def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm's step-down adjustment: the i-th smallest p is multiplied by (m - i), never below an earlier one, capped at 1."""
    ordered, adjusted, running = sorted(p_values.items(), key=lambda item: item[1]), {}, 0.0
    for rank, (key, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        adjusted[key] = running
    return adjusted


def cohen_kappa(first: list[str], second: list[str]) -> float:
    """Agreement between two raters beyond what chance alone gives."""
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / n
    labels = set(first) | set(second)
    expected = sum((first.count(label) / n) * (second.count(label) / n) for label in labels)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def cohen_h(p1: float, p2: float) -> float:
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))


def seeds_needed(effects_by_seed: list[float], effect: float) -> int:
    """Three seeds by default; five when the spread between seeds is larger than the effect itself."""
    spread = max(effects_by_seed) - min(effects_by_seed) if effects_by_seed else 0.0
    return MORE_SEEDS if spread > abs(effect) else MIN_SEEDS
