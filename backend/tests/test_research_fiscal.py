# test_research_fiscal.py: a public freshness benchmark (FiscalQA Pro) in the Lab. The nugget grader scores as FiscalQA's own
# scorer does (French thousands, decimal commas, thirds; every required nugget) and labels a sibling version's value stale.
# A tiny pack in the converter's own format (one article in two versions, three canaries, nuggets, FiscalQA's prompt) runs
# through the real S1, S2, S11 and S5: under C1 each version ends on its own date, so both dates answer fresh; under C0 the
# old version stays and the later question sees both. Uses: research/grade_nuggets.py, research/runner.py,
# scripts/research_convert_fiscalqa.py (its helpers), tests/research_packs_world.py (zip).
import re
import uuid

import pytest

from app.research import experiment_store, grade_nuggets, lab_embed, packs, prereg, runner
from app.research.contracts import Experiment, Hypothesis
from app.research.pack_schemas import Nugget
from tests.research_packs_world import zipped
from tests.test_research_security import script

# Config
MAKE = script("research_convert_fiscalqa")
OLD, NEW = "Le plafond est fixé à 1 370 € par foyer.", "Le plafond est fixé à 2 450 € par foyer."
H1 = Hypothesis(id="H1", metric="stale_answer_rate", comparator="at_most", threshold=-0.25, conditions=["C1", "C0"], test="paired_bootstrap")


def nugget(query_id: str, target: float) -> list[Nugget]:
    return [Nugget(query_id=query_id, nugget_id=f"{query_id}-art", kind="regex", pattern=r"\b1414\b"),
            Nugget(query_id=query_id, nugget_id=f"{query_id}-val", kind="numeric_tol", target=target, tol=1.0)]


# --- The scorer

@pytest.mark.parametrize("answer, target, expected", [
    ("Selon l'article 1414, le plafond est de 1 370 F.", 1370, True),
    ("Article 1414 : 1 370 €.", 1370, True),  # a narrow no-break space between thousands
    ("Article 1414, taux de 5,5 %.", 5.5, True),
    ("Article 1414 : 33 1/3 %.", 33.3333, True),
    ("Le plafond est de 1 370 €.", 1370, False),  # the article is a required nugget too
])
def test_scoring_matches_fiscalqa(answer, target, expected):
    assert grade_nuggets.strict(answer, nugget("q", target)) is expected


def test_another_dates_value_is_stale_and_both_is_mixed():
    own, other = nugget("q2015", 2450), nugget("q2005", 1370)
    assert grade_nuggets.grade("Article 1414 : 2 450 €.", own, [other]) == "fresh"
    assert grade_nuggets.grade("Article 1414 : 1 370 €.", own, [other]) == "stale"
    assert grade_nuggets.grade("Article 1414 : 1 370 € puis 2 450 €.", own, [other]) == "mixed"
    assert grade_nuggets.grade("Je ne sais pas.", own, [other]) == "wrong"


# --- A tiny pack, end to end

def tiny_pack() -> dict:
    files = {"documents/V1.md": MAKE.document("V1", MAKE.title_of("1414", "V1"), OLD, "2000-01-01", "2010-01-01"),
             "documents/V2.md": MAKE.document("V2", MAKE.title_of("1414", "V2"), NEW, "2010-01-01", None)}
    queries = [{"query_id": q, "text": "Quel est le plafond de l'article 1414 du CGI ?", "as_of": on, "fact_id": "A1414", "kind": "stale_sensitive"}
               for q, on in (("q2005", "2005-06-01"), ("q2015", "2015-06-01"))]
    rows = [n.model_dump(exclude_none=True) for n in [*nugget("q2005", 1370), *nugget("q2015", 2450)]]
    facts = [{"fact_id": "A1414", "subject": "Article 1414 du CGI", "new_value": "", "new_doc_id": "V2", "new_sentence": "Article 1414 du CGI"}]
    gold = [{"query_id": "q2005", "expected_value": "1 370 €"}, {"query_id": "q2015", "expected_value": "2 450 €"}]
    for name, value in MAKE.CANARIES:
        sentence = f"La valeur de contrôle {name} est fixée à {value} euros."
        files[f"documents/C-{name}.md"] = MAKE.document(f"C-{name}", f"Note {name}", sentence, "1999-01-01", None)
        queries.append({"query_id": f"canary-{name}", "text": f"Quelle est la valeur de contrôle {name} ?", "as_of": "2015-06-01", "fact_id": f"c{name}", "kind": "canary"})
        facts.append({"fact_id": f"c{name}", "subject": name, "new_value": str(value), "new_doc_id": f"C-{name}", "new_sentence": sentence})
        gold.append({"query_id": f"canary-{name}", "expected_value": str(value)})
        rows.append({"query_id": f"canary-{name}", "nugget_id": f"c{name}", "kind": "numeric_tol", "target": value, "tol": 0.5})
    files.update({"queries.jsonl": MAKE.jsonl(queries), "gold.jsonl": MAKE.jsonl(gold), "facts.jsonl": MAKE.jsonl(facts), "nuggets.jsonl": MAKE.jsonl(rows),
                  "answer_prompt.txt": MAKE.ANSWER_PROMPT, "README.md": "test\n"})
    files["manifest.json"] = MAKE.json.dumps({"kind": "freshness", "name": "tiny_fiscal", "version": "1", "company": "t", "timezone": "Europe/Paris", "currency": "EUR",
                                              "created_by": "tests", "license": "test", "files": ["README.md", "answer_prompt.txt", "nuggets.jsonl"]})
    return packs.parse_pack(packs.read_zip(zipped(files)))


def reader(prompt: str) -> tuple[str, dict]:
    """Answers from the context only, in FiscalQA's prompt: the article and every amount it reads, or a control value."""
    assert prompt.startswith("Tu es un assistant juridique fiscal")  # the pack's own prompt, not Execution_V1's
    context = prompt.split('"""')[1]
    control = re.search(r"valeur de contrôle K0\d est fixée à (\d+)", context)
    amounts = re.findall(r"fixé à (\d[\d ]*) €", context)
    return (control.group(1) if control and "contrôle" in prompt.split("Question :")[1] else f"Article 1414 : {' puis '.join(amounts)} €."), {"in": 900, "out": 20}


def test_titles_carry_no_order():
    first, second = MAKE.title_of("1414", "LEGIARTI000006312074"), MAKE.title_of("1414", "LEGIARTI000006312075")
    assert first != second and first.startswith("Article 1414 du CGI (") and not re.search(r"\b(19|20)\d\d\b", first + second)


def test_versions_end_on_their_own_dates_under_c1_and_linger_under_c0():
    pack = tiny_pack()
    assert not pack["errors"] and len(pack["extra"]["nuggets.jsonl"]) == 7
    preregs, experiments = prereg.MemoryPreregs(), experiment_store.MemoryExperiments()
    locked = preregs.lock(preregs.create(prereg.draft("policies", "Fiscal", [H1])).id, "founder")
    experiment = experiments.create(Experiment(id=str(uuid.uuid4()), paper="policies", pack_id="p", prereg_id=locked.id, source="lab", conditions=["C0", "C1"], seeds=[1],
                                               trials=1, models={"answer": "claude-haiku-5-5"}, budget_usd=1.0, config_sha256="c", git_commit="g", status="estimated"))
    assert runner.run(experiment.id, experiments, preregs, lambda pack_id: pack, answer=reader, parts=frozenset()) == "finished", experiments.get(experiment.id).notes
    labels = {(c.condition, c.case_id): c.outcome["label"] for c in experiments.cases_of(experiment.id)}
    assert labels[("C1", "q2005")] == labels[("C1", "q2015")] == "fresh"
    assert labels[("C0", "q2005")] == "fresh" and labels[("C0", "q2015")] == "mixed"  # the ended version still answers under C0
    assert experiments.get(experiment.id).notes["ingest"]["C1"]["closed_documents"] == 1


def test_a_french_batch_stays_under_the_minute_limit():
    text = "Le plafond est fixé à 1 370 € par foyer, sous réserve des dispositions de l'article 1414 du code général des impôts. " * 40
    for group in lab_embed.batches([text] * 30):
        assert sum(len(t) for t in group) / 3 <= lab_embed.EMBED_BATCH_TOKENS + len(text) / 3  # counted at 3 characters a token
