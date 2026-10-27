# test_research_runner.py: the freshness runner (Research Lab step 6) with a scripted answerer that reads only the context
# S5 gave it, so every outcome is decided by what the real pipeline retrieved. A run grades by rule, stores each case once,
# resumes after a crash without asking twice, stops at its cost cap, refuses an unlocked preregistration, lets one of two
# workers run, and judges the hypothesis with the gates. Real Postgres, Valkey, S3 and Redpanda when Docker is up.
# Uses: research/runner.py, research/grade_freshness.py, research/experiment_store.py, tests/research_packs_world.py.
import re
import threading
import uuid
from datetime import timedelta

import pytest

from app.pipeline.adapters import missing_infra
from app.research import experiment_store, grade_freshness, lab_tenant, packs, prereg, runner, store
from app.research.contracts import Experiment, Hypothesis
from tests.research_packs_world import CANARIES, files

# Config
PACK = packs.parse_pack(files())
CANARY_VALUES = {f"K0{i + 1}": value for i, (_, _, value) in enumerate(CANARIES)}
H1 = Hypothesis(id="H1", metric="stale_answer_rate", comparator="at_most", threshold=-0.5, conditions=["C1", "C0"], test="paired_bootstrap", diagnosis_stage=2)


def scripted(prompt: str) -> tuple[str, dict]:
    """Answers from the context only: the first refund window it reads, or the canary value if its sentence is there."""
    context, question = prompt.split("Retrieved context:")[1].split("Question:")
    window = re.search(r"refund within (\d+) days", context)
    canary = re.search(r"answer for (K\d+)", question)
    if canary:
        value = CANARY_VALUES[canary.group(1)]
        return (value if value in context else grade_freshness.REFUSAL), {"in": 1000, "out": 10}
    return (f"{window.group(1)} days" if window else grade_freshness.REFUSAL), {"in": 1000, "out": 10}


def world(budget: float = 1.0, hypotheses: list[Hypothesis] = (H1,), lock: bool = True):
    preregs, experiments = prereg.MemoryPreregs(), experiment_store.MemoryExperiments()
    written = preregs.create(prereg.draft("policies", "Freshness", list(hypotheses)))
    if lock:
        preregs.lock(written.id, "founder")
    experiment = experiments.create(Experiment(id=str(uuid.uuid4()), paper="policies", pack_id="pack", prereg_id=written.id, source="lab", conditions=["C0", "C1"],
                                               seeds=[1, 2, 3], trials=1, models={"answer": "claude-haiku-5-5"}, budget_usd=budget, config_sha256="c", git_commit="g", status="estimated"))
    return experiments, preregs, experiment


def run(experiments, preregs, experiment, answer=scripted, parts=frozenset()):
    return runner.run(experiment.id, experiments, preregs, lambda pack_id: PACK, answer=answer, parts=parts)


# --- Grading by rule

@pytest.mark.parametrize("answer, label", [("Customers have 45 days.", "fresh"), ("Within 30 days of delivery.", "stale"), ("It was 30 days, now 45 days.", "mixed"),
                                           ("NOT_IN_CONTEXT", "refused"), ("45 hours", "wrong"), ("No idea.", "wrong")])
def test_answers_are_graded_by_rule(answer, label):
    assert grade_freshness.grade(answer, "45 days", ["30 days"]) == label


def test_units_symbols_and_text_values():
    assert grade_freshness.grade("A fee of 8% applies.", "8 percent", ["15 percent"]) == "fresh"
    assert grade_freshness.grade("They take 5 business days.", "5 business days", ["10 business days"]) == "fresh"
    assert grade_freshness.grade("The operations governance function owns it.", "the operations governance function", []) == "fresh"
    assert grade_freshness.grade("1,000 dollars", "1000 dollars", []) == "fresh"


# --- A run

def test_a_run_grades_every_case_once_and_judges_the_hypothesis():
    experiments, preregs, experiment = world()
    assert run(experiments, preregs, experiment) == "finished"
    cases = experiments.cases_of(experiment.id)
    assert len(cases) == 2 * 3 * 4  # conditions x seeds x questions
    values = {(v.metric_key, v.condition): v for v in experiments.results_of(experiment.id)[0]}
    assert values[("stale_answer_rate", "C1")].value == 0.0 and values[("canary_accuracy", "C0")].value == 1.0
    assert values[("stale_answer_rate", "C0")].value > values[("stale_answer_rate", "C1")].value  # C0 still retrieves the 30 day chunk
    verdict = experiments.results_of(experiment.id)[1][0]
    assert verdict.hypothesis_id == "H1" and verdict.ci_low <= verdict.effect <= verdict.ci_high
    assert experiments.get(experiment.id).notes["gates"]["passed"]


def test_a_crash_resumes_without_asking_any_question_twice():
    experiments, preregs, experiment = world()
    asked: list[str] = []

    def crashing(prompt: str):
        if len(asked) == 7:
            raise RuntimeError("model went away")
        asked.append(prompt)
        return scripted(prompt)

    assert run(experiments, preregs, experiment, crashing) == "failed"
    assert "model went away" in experiments.get(experiment.id).notes["error"] and len(experiments.cases_of(experiment.id)) == 7
    asked_again: list[str] = []
    assert run(experiments, preregs, experiment, lambda p: (asked_again.append(p), scripted(p))[1]) == "finished"
    assert len(asked_again) == 24 - 7 and len(experiments.cases_of(experiment.id)) == 24


def test_the_cost_cap_stops_the_run_cleanly_with_what_it_has():
    experiments, preregs, experiment = world(budget=0.0008)  # a few Haiku answers at 1,000 tokens each
    assert run(experiments, preregs, experiment) == "budget_reached"
    stopped = experiments.get(experiment.id)
    assert 0 < len(experiments.cases_of(experiment.id)) < 24 and stopped.cost_usd <= stopped.budget_usd


def test_a_preregistration_that_is_not_locked_never_runs():
    experiments, preregs, experiment = world(lock=False)
    assert run(experiments, preregs, experiment) == "failed"
    assert experiments.get(experiment.id).notes["error"] == "preregistration_not_locked_or_changed" and experiments.cases_of(experiment.id) == []


def test_a_bad_baseline_makes_every_verdict_invalid():
    experiments, preregs, experiment = world()
    assert run(experiments, preregs, experiment, lambda prompt: (grade_freshness.REFUSAL, {"in": 10, "out": 1})) == "invalid_run"
    assert {c.verdict for c in experiments.results_of(experiment.id)[1]} == {"invalid_run"}


def test_one_of_two_workers_runs_and_a_silent_one_is_replaced():
    experiments, _, experiment = world()
    now = experiment_store.utc_now()
    assert experiments.claim(experiment.id, "w1", now) and not experiments.claim(experiment.id, "w2", now)
    assert experiments.claim(experiment.id, "w2", now + timedelta(minutes=3))  # w1 stopped beating


# --- Real infra

@pytest.mark.skipif(bool(missing_infra(lab_tenant.LAB_PARTS)), reason="lab infra not answering")
def test_on_real_infra_a_run_is_stored_in_postgres_and_its_labs_are_gone_after():
    connection = store.connect()
    preregs, experiments = prereg.PostgresPreregs(connection), experiment_store.PostgresExperiments(connection)
    written = preregs.create(prereg.draft("policies", f"Runner {uuid.uuid4()}", [H1]))
    preregs.lock(written.id, "founder")
    experiment = experiments.create(Experiment(id=str(uuid.uuid4()), paper="policies", prereg_id=written.id, source="lab", conditions=["C0", "C1"], seeds=[1],
                                               trials=1, models={"answer": "claude-haiku-5-5"}, budget_usd=1.0, config_sha256="c", git_commit="g", status="estimated"))
    try:
        outcome = runner.run(experiment.id, experiments, preregs, lambda pack_id: PACK, answer=scripted, parts=lab_tenant.LAB_PARTS)
        stored = experiments.get(experiment.id)
        assert outcome == "finished", stored.notes
        assert len(experiments.cases_of(experiment.id)) == 8 and all(stored.notes["teardown"].values())
        assert experiments.results_of(experiment.id)[1][0].hypothesis_id == "H1"
        assert all(set(lab_tenant.leftovers(lab).values()) == {0} for lab in [f"lab_{uuid.uuid5(uuid.UUID(experiment.id), c).hex}" for c in ("C0", "C1")])
    finally:
        connection.execute("DELETE FROM research.experiments WHERE id = %s", (experiment.id,))
        with store.connect() as cleanup, cleanup.transaction():
            cleanup.execute("ALTER TABLE research.preregistrations DISABLE TRIGGER prereg_locked")
            cleanup.execute("DELETE FROM research.preregistrations WHERE id = %s", (written.id,))
            cleanup.execute("ALTER TABLE research.preregistrations ENABLE TRIGGER prereg_locked")


@pytest.mark.skipif(bool(missing_infra(frozenset({"postgres"}))), reason="no Postgres")
def test_on_postgres_four_workers_claim_at_once_and_one_wins():
    connection = store.connect()
    experiments = experiment_store.PostgresExperiments(connection)
    experiment = experiments.create(Experiment(id=str(uuid.uuid4()), paper="policies", source="lab", conditions=["C0"], seeds=[1], trials=1,
                                               models={"answer": "claude-haiku-5-5"}, budget_usd=1.0, config_sha256="c", git_commit="g", status="estimated"))
    won: list[bool] = []

    def claim(worker: str) -> None:
        with store.connect() as own:
            won.append(experiment_store.PostgresExperiments(own).claim(experiment.id, worker, experiment_store.utc_now()))

    try:
        workers = [threading.Thread(target=claim, args=(f"w{i}",)) for i in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert sorted(won) == [False, False, False, True]
    finally:
        connection.execute("DELETE FROM research.experiments WHERE id = %s", (experiment.id,))


# --- Embeddings in the lab

def test_each_string_is_embedded_once_and_a_rate_limit_is_waited_out():
    from app.pipeline.embeddings import VoyageError
    from app.research import lab_embed
    calls, waits = [], []

    def flaky(texts, input_type):
        calls.append(list(texts))
        if len(calls) == 1:
            raise VoyageError("voyage /embeddings answered 429")
        return [[float(len(t))] for t in texts]

    embed = lab_embed.once_each(flaky, sleep=waits.append)
    first = embed([f"lab-test {uuid.uuid4()}", "lab-test shared"], "query")
    again = embed(["lab-test shared"], "query")
    assert waits == [5] and len(calls) == 2 and again == [first[1]]  # asked again only after the wait, never for a known string
    assert lab_embed.keep_order("q", ["a", "b", "c"]) == [3.0, 2.0, 1.0]


def test_batches_stay_under_the_token_cap_and_keep_every_string_in_order():
    from app.research import lab_embed
    texts = [f"t{i} " + "word " * 300 for i in range(40)]  # about 375 tokens each
    groups = lab_embed.batches(texts)
    assert [t for g in groups for t in g] == texts and len(groups) > 1
    assert all(sum(len(t) // 4 + 1 for t in g) <= lab_embed.EMBED_BATCH_TOKENS for g in groups)


def test_text_answers_match_by_meaning_words_and_yes_no_by_their_first_word():
    assert grade_freshness.grade("Figures are stated in the reporting currency of Nyrivell Dynamics.", "the reporting currency of the company", []) == "fresh"
    assert grade_freshness.grade("No. Superseded versions are never withdrawn from the archive.", "no, they are retained", []) == "fresh"
    assert grade_freshness.grade("Yes, they are withdrawn.", "no, they are retained", []) == "wrong"
    assert grade_freshness.grade("A single published source.", "one", []) == "wrong"  # a synonym is beyond a rule; the report says so
