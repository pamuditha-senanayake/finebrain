# test_research_skills.py: the skills paper (Research Lab step 13). The generated refund pack keeps to its alphabet; pass^k
# counts only cases run the full number of times and matches the unbiased formula; a skills experiment runs refund cases
# trial after trial through the real pipeline (S9 in shadow) with a scripted agent, ends each as the refund policy says,
# keeps each run's activities, and reports task success and pass^1 to pass^n with intervals.
# Uses: research/skills_lab.py, research/results.py, research/runner.py, scripts/research_make_refund_skills_pack.py.
import json
import uuid

from app.research import experiment_store, packs, prereg, results, runner, skills_lab
from app.research.contracts import CaseResult, Experiment, Hypothesis
from tests.test_research_security import MODELS, script

# Config
MAKE = script("research_make_refund_skills_pack")
PACK = packs.parse_pack(packs.read_zip(MAKE.build_pack()))


def case(task: str, trial: int, met: bool) -> CaseResult:
    return CaseResult(experiment_id="e", condition="B1", seed=1, trial=trial, case_id=task, outcome={"benign": True, "goal_met": met}, passed=met)


def test_the_pack_holds_every_ending_and_keeps_to_its_alphabet():
    endings = [t.expected_final_state["outcome"] for t in PACK["main"]]
    assert {e: endings.count(e) for e in set(endings)} == {"resolved": 8, "awaiting_approval": 6, "escalated": 2} and not PACK["errors"]
    alphabet = set(json.loads(PACK["files"]["alphabet.json"]))
    assert all(f"'{a}'" in PACK["files"]["normative_model.ptree"] for a in ("retrieve_context", "propose_issue_refund", "await_approval", "act_escalate"))
    assert set(MAKE.trace(__import__("random").Random(1))) <= alphabet


def test_pass_k_counts_complete_cases_only():
    cases = [case("a", t, t < 3) for t in range(1, 5)] + [case("b", t, True) for t in range(1, 5)] + [case("c", 1, True)]  # c ran once: it waits
    found, n = results.successes_by_task(cases, "B1")
    assert (found, n) == ({"a": 2, "b": 4}, 4)
    by = {v.metric_key: v.value for v in results.pass_values("e", cases, ["B1"])}
    assert by["pass_hat_1"] == (2 / 4 + 1) / 2 and by["pass_hat_2"] == (1 / 6 + 1) / 2 and by["pass_hat_4"] == 0.5 and "pass_hat_8" not in by


def test_a_skills_run_ends_each_case_as_the_policy_says_and_reports_pass_k():
    pack = {**PACK, "main": [t for t in PACK["main"] if t.task_id in ("K-01", "K-09", "K-12", "K-15")]}  # refund, late, large, unknown payment
    preregs, experiments = prereg.MemoryPreregs(), experiment_store.MemoryExperiments()
    hypotheses = [Hypothesis(id="H1", metric="pass_hat_2", comparator="at_least", threshold=0.5, conditions=["B1"], test="bootstrap_mean")]
    locked = preregs.lock(preregs.create(prereg.draft("skills", "Skills", hypotheses)).id, "founder")
    experiment = experiments.create(Experiment(id=str(uuid.uuid4()), paper="skills", pack_id="p", prereg_id=locked.id, source="lab", conditions=["B0", "B1"], seeds=[1],
                                               trials=2, models={"answer": "claude-sonnet-5-5"}, budget_usd=5.0, config_sha256="c", git_commit="g", status="estimated"))
    assert runner.estimate(experiment, pack)["cases"] == 16
    assert runner.run(experiment.id, experiments, preregs, lambda pack_id: pack, answer=MODELS, parts=frozenset()) == "finished", experiments.get(experiment.id).notes
    cases = experiments.cases_of(experiment.id)
    ending = {c.case_id: c.outcome["outcome"] for c in cases if c.condition == "B1"}
    assert ending == {"K-01": "resolved", "K-09": "awaiting_approval", "K-12": "awaiting_approval", "K-15": "escalated"}
    assert all(c.outcome["goal_met"] and c.outcome["activities"][0] == "retrieve_context" for c in cases)
    values, judged = experiments.results_of(experiment.id)
    by = {(v.metric_key, v.condition): v.value for v in values}
    assert by[("task_success", "B1")] == by[("pass_hat_2", "B1")] == 1.0 and judged[0].verdict == "supported"


def test_b0_keeps_the_tools_but_not_the_steps():
    bare, written = skills_lab.seed_for(skills_lab.CONDITIONS["B0"]), skills_lab.seed_for(skills_lab.CONDITIONS["B1"])
    skill = lambda seed: next(s for s in seed["skills"] if s["id"] == skills_lab.SKILL)
    assert skill(bare)["steps"] == skills_lab.BARE_STEPS and skill(bare)["allowed_tools"] == skill(written)["allowed_tools"]
    assert skill(written)["steps"] != skills_lab.BARE_STEPS


def test_the_tau3_adapter_reads_pass_k_and_cost_from_taus_results():
    tau3 = script("research_tau3")
    sims = [{"task_id": t, "trial": i, "reward_info": {"reward": 1.0 if (t == "a" or i < 2) else 0.0}, "termination_reason": "user_stop",
             "messages": [{"usage": {"prompt_tokens": 1000, "completion_tokens": 100}}]} for t in ("a", "b") for i in range(4)]
    found = tau3.summarize({"info": {}, "simulations": sims}, "claude-haiku-5-5")
    assert (found["tasks"], found["trials"], found["errored"]) == (2, 4, 0)
    assert found["curve"]["pass_hat_1"]["value"] == (1 + 0.5) / 2 and found["curve"]["pass_hat_4"]["value"] == 0.5 and "pass_hat_8" not in found["curve"]
    assert found["cost_usd"] == round((8000 * 0.10 + 800 * 0.50) / 1_000_000, 4)
    assert not tau3.version_ok({"info": {"tau2_version": "1.0.0"}}) and tau3.version_ok({"info": {"tau2_version": "2.0.0"}})
