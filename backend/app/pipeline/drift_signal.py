# drift_signal.py: the S13 drift signal (Research Lab P5). Finds where a process changed in a stream of cases, in arrival
# order: two adjacent windows of cases are compared on every feature (which activities a case has, which directly follow
# which, and how long each activity takes), and an alarm sounds when one feature differs past both a statistical bar and a
# size bar. After an alarm the detector waits two windows, so one change gives one alarm. Pure and deterministic: the same
# cases give the same alarms. Used by: research/drift_eval.py, scripts/research_drift_benchmark.py. Uses: nothing local.
import math
from dataclasses import dataclass

# Config
WINDOW, STEP = 500, 50  # cases per window, and how often the two windows are compared
Z_BAR = 8.0  # how many standard errors apart: strict, because every feature is tested at every step
MIN_SHARE_GAP = 0.10  # a share of cases (an activity present, a pair following) must move at least 10 points
MIN_LOG_GAP = 0.5  # an activity's typical duration must change by at least e^0.5, about 1.65 times
MIN_TIMED = 30  # cases in each window that timed the activity, before its duration is compared


@dataclass
class Alarm:
    at: int  # the case index when the alarm sounded
    feature: str
    statistic: float


def features_of(case: dict) -> tuple[set[str], dict[str, float]]:
    """A case's binary features (activities present, directly-follows pairs) and its mean log duration per activity."""
    activities = case["activities"]
    present = {f"has:{a}" for a in activities} | {f"follows:{a}>{b}" for a, b in zip(activities, activities[1:])}
    timed = {a: sum(math.log1p(max(0.0, d)) for d in ds) / len(ds) for a, ds in case.get("durations", {}).items() if ds}
    return present, timed


def detect(cases: list[dict], window: int = WINDOW, step: int = STEP) -> list[Alarm]:
    """Every alarm over the stream. A case is {"activities": [...], "durations": {activity: [seconds]}}."""
    rows = [features_of(c) for c in cases]
    names = sorted({f for present, _ in rows for f in present})
    timed_names = sorted({a for _, timed in rows for a in timed})
    share = {f: prefix([1.0 if f in present else 0.0 for present, _ in rows]) for f in names}
    moments = {a: (prefix([1.0 if a in t else 0.0 for _, t in rows]), prefix([t.get(a, 0.0) for _, t in rows]), prefix([t.get(a, 0.0) ** 2 for _, t in rows]))
               for a in timed_names}
    alarms, t = [], 2 * window
    while t <= len(rows):
        found = strongest(share, moments, t - 2 * window, t - window, t, window)
        if found and found[1] >= Z_BAR:
            alarms.append(Alarm(at=t, feature=found[0], statistic=round(found[1], 2)))
            t += 2 * window  # one change, one alarm
            continue
        t += step
    return alarms


def prefix(values: list[float]) -> list[float]:
    sums = [0.0]
    for v in values:
        sums.append(sums[-1] + v)
    return sums


def between(sums: list[float], start: int, end: int) -> float:
    return sums[end] - sums[start]


def strongest(share: dict, moments: dict, a: int, b: int, c: int, window: int) -> tuple[str, float] | None:
    """The feature that differs most between cases [a, b) and [b, c), counting only differences past the size bars."""
    best = None
    for name, sums in share.items():
        p1, p2 = between(sums, a, b) / window, between(sums, b, c) / window
        pooled = (p1 + p2) / 2
        if abs(p2 - p1) >= MIN_SHARE_GAP and 0 < pooled < 1:
            z = abs(p2 - p1) / math.sqrt(pooled * (1 - pooled) * 2 / window)
            best = max(best or (name, 0.0), (name, z), key=lambda x: x[1])
    for name, (count, total, squares) in moments.items():
        n1, n2 = between(count, a, b), between(count, b, c)
        if min(n1, n2) < MIN_TIMED:
            continue
        m1, m2 = between(total, a, b) / n1, between(total, b, c) / n2
        v1, v2 = max(between(squares, a, b) / n1 - m1 * m1, 1e-9), max(between(squares, b, c) / n2 - m2 * m2, 1e-9)
        if abs(m2 - m1) >= MIN_LOG_GAP:
            z = abs(m2 - m1) / math.sqrt(v1 / n1 + v2 / n2)
            best = max(best or (f"takes:{name}", 0.0), (f"takes:{name}", z), key=lambda x: x[1])
    return best
