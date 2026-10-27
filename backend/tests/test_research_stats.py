# test_research_stats.py: the Lab's statistics against values from textbooks and worked examples (Research Lab step 5).
# Wilson (Newcombe 1998), exact McNemar (1 and 9 discordant pairs), Holm (step-down), Cohen's kappa (the 20/5/10/15
# table), Cohen's h, the rule of three, pass^k, and bootstrap intervals that repeat exactly. Uses: research/stats.py.
import pytest

from app.research import stats


def test_wilson_matches_the_published_intervals():
    assert stats.wilson(0, 10) == pytest.approx((0.0, 0.2775), abs=1e-4)
    assert stats.wilson(5, 10) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    assert stats.wilson(10, 10) == pytest.approx((0.7225, 1.0), abs=1e-4)
    assert stats.wilson(0, 0) == (0.0, 1.0)  # nothing measured: anything is possible


def test_zero_events_use_the_rule_of_three_and_300_episodes_cover_one_percent():
    assert stats.rule_of_three(300) == pytest.approx(0.01)
    assert stats.episodes_for_zero_rate(0.01) == 300


def test_exact_mcnemar_counts_only_discordant_pairs():
    assert stats.mcnemar_exact(1, 9)["p"] == pytest.approx(22 / 1024)  # 2 x (C(10,0) + C(10,1)) / 2^10
    assert stats.mcnemar_exact(5, 5)["p"] == 1.0 and stats.mcnemar_exact(0, 0)["p"] == 1.0
    assert stats.discordant({"q1": True, "q2": False, "q3": True}, {"q1": False, "q2": False, "q3": True, "q4": True}) == (1, 0)


def test_pass_hat_k_is_the_unbiased_estimator():
    assert stats.pass_hat_k(4, 8, 2) == pytest.approx(6 / 28)
    assert stats.pass_hat_k(8, 8, 8) == 1.0 and stats.pass_hat_k(7, 8, 8) == 0.0
    assert stats.pass_hat_k(4, 8, 1) == 0.5
    with pytest.raises(ValueError):
        stats.pass_hat_k(1, 4, 8)


def test_holm_steps_down_and_never_decreases():
    adjusted = stats.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.005})
    assert adjusted == pytest.approx({"d": 0.02, "a": 0.03, "c": 0.06, "b": 0.06})
    assert stats.holm({"only": 0.7, "other": 0.9}) == {"only": 1.0, "other": 1.0}


def test_cohen_kappa_and_h_match_the_worked_examples():
    first = ["yes"] * 25 + ["no"] * 25
    second = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
    assert stats.cohen_kappa(first, second) == pytest.approx(0.4)
    assert stats.cohen_kappa(["a", "a"], ["a", "a"]) == 1.0
    assert stats.cohen_h(0.5, 0.3) == pytest.approx(0.4115, abs=1e-4)


def test_the_paired_bootstrap_moves_whole_tasks_and_repeats_exactly():
    same = {f"t{i}": [1.0, 0.0, 1.0] for i in range(30)}
    nothing = stats.paired_bootstrap(same, same)
    assert (nothing["effect"], nothing["low"], nothing["high"], nothing["p"]) == (0.0, 0.0, 0.0, 1.0)

    better = {f"t{i}": [1.0, 1.0, 1.0] for i in range(30)}
    worse = {f"t{i}": [0.0, 0.0, 1.0] for i in range(30)}
    clear = stats.paired_bootstrap(better, worse)
    assert clear["effect"] == pytest.approx(2 / 3) and clear["p"] == 0.0 and clear["n"] == 30
    assert stats.paired_bootstrap(better, worse) == clear  # seeded: the same input, the same interval


def test_a_bootstrap_mean_brackets_the_mean():
    found = stats.bootstrap_mean([0.0, 1.0] * 50)
    assert found["estimate"] == 0.5 and 0.38 < found["low"] < 0.42 and 0.58 < found["high"] < 0.62
    assert stats.bootstrap_mean([]) == {"estimate": 0.0, "low": 0.0, "high": 0.0, "n": 0}


def test_five_seeds_when_seeds_disagree_more_than_the_effect():
    assert stats.seeds_needed([0.10, 0.12, 0.11], 0.10) == 3
    assert stats.seeds_needed([-0.05, 0.20, 0.10], 0.10) == 5
