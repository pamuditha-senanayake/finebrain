# test_drift.py: the S13 drift signal (P5), its scoring (Adams et al.: a lag window after each drift, each found once) and
# the tau Drift generator. A stream with one injected activity, one slowed activity, and none, gives one alarm, one alarm
# and none; scores count delay and false alarms; an alarm the undrifted log also raises is a real change, not a false one;
# XES reads with durations; tau Drift's gold follows the version valid on each date. Uses: pipeline/drift_signal.py,
# research/drift_eval.py, research/tau_drift.py.
import random

from app.pipeline import drift_signal
from app.research import drift_eval, tau_drift


def stream(change_at: int | None, inserted: bool = False, slowed: bool = False, n: int = 3000) -> list[dict]:
    rng, cases = random.Random(7), []
    for i in range(n):
        after = change_at is not None and i >= change_at
        activities = ["A", "B", *(["X"] if inserted and after else []), "C"]
        cases.append({"activities": activities, "durations": {"B": [rng.uniform(50, 70) * (5 if slowed and after else 1)]}})
    return cases


def test_an_inserted_activity_is_found_once_and_soon():
    alarms = drift_signal.detect(stream(1500, inserted=True))
    assert len(alarms) == 1 and 1500 < alarms[0].at <= 2000 and alarms[0].feature in ("has:X", "follows:B>X", "follows:X>C", "follows:B>C")


def test_a_slowed_activity_is_found_and_a_steady_stream_raises_nothing():
    slowed = drift_signal.detect(stream(1500, slowed=True))
    assert len(slowed) == 1 and slowed[0].feature == "takes:B"
    assert drift_signal.detect(stream(None)) == []


def test_scoring_counts_delay_false_alarms_and_real_changes():
    got = drift_eval.score([1600, 2600, 2900], [(1500, 1500)], lag=500)
    assert (got["found"], got["delay_traces"], got["false_alarm_rate"]) == (1, 100.0, 2 / 3)
    real = drift_eval.score([1600, 2600, 2900], [(1500, 1500)], lag=500, natural=[2650])  # 2600 and 2900 are where the undrifted log changes too
    assert (real["recall"], real["false_alarm_rate"], real["natural"]) == (1.0, 0.0, 2)
    assert drift_eval.score([4000], drift_eval.drifts_of([3000, 3800], "gradual"), lag=500)["found"] == 1  # inside a gradual transition


def test_xes_reads_activities_and_durations(tmp_path):
    path = tmp_path / "tiny.xes"
    path.write_text('<?xml version="1.0"?><log xmlns="http://www.xes-standard.org/"><trace><string key="concept:name" value="c1"/>'
                    '<event><string key="concept:name" value="A"/><date key="start:timestamp" value="2026-01-01T10:00:00+00:00"/>'
                    '<date key="time:timestamp" value="2026-01-01T10:01:30.000000001+00:00"/></event>'
                    '<event><string key="concept:name" value="B"/><date key="time:timestamp" value="2026-01-01T10:05:00Z"/></event></trace></log>')
    assert drift_eval.read_xes(str(path)) == [{"activities": ["A", "B"], "durations": {"A": [90.0]}}]


def test_tau_drift_gold_follows_the_version_of_each_date():
    found = tau_drift.tasks(random.Random(1))
    late = next(t for t in found if t["as_of"] >= "2026-05-01" and t["as_of"] < "2026-07-01" and 31 <= t["initial_state"]["age_days"] <= 45
                and t["initial_state"]["amount_minor"] <= 5_000_000)
    assert late["expected_actions"][0]["route"] == "execute" and late["initial_state"]["changed"]  # 45 days that spring; 30 before, 21 after
    versions = tau_drift.policies()
    assert [v["params"]["window_days"] for v in versions] == [30, 45, 45, 21] and versions[-1]["valid_to"] is None
    points = tau_drift.drift_points(found)
    assert [p["change_at_time"] for p in points] == ["2026-05-01", "2026-07-01", "2026-09-01"] and all(found[p["change_at_case_index"]]["as_of"] >= p["change_at_time"] for p in points)
