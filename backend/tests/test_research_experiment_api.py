# test_research_experiment_api.py: the experiment API (Research Lab step 6). Creating names every problem before money is
# spent (an unlocked preregistration, C2, a condition the hypotheses need, a cap over the limit, a pack for another paper)
# and saves the estimate; starting runs in the background; progress, results and one case at a time read back.
# Uses: research/routes.py, research/experiment_routes.py, tests/test_research_runner.py (scripted answerer), tests/research_packs_world.py.
import time

from fastapi.testclient import TestClient

from app.research import experiment_store, pack_store, prereg, runner
from app.research.routes import create_research_app
from tests.research_packs_world import files, zipped
from tests.test_research_api import PEOPLE, FakeConnection
from tests.test_research_runner import H1, scripted

# Config
FOUNDER = {"x-persona": "h-founder"}


def lab_client(monkeypatch) -> tuple[TestClient, str, str]:
    """A Lab app on memory stores with the tiny pack uploaded and H1 locked; the model is the scripted answerer."""
    monkeypatch.setattr(runner, "make_answerer", lambda model: scripted)
    kept, preregs, experiments = pack_store.MemoryPacks(), prereg.MemoryPreregs(), experiment_store.MemoryExperiments()
    app = create_research_app(connect=FakeConnection, people=PEOPLE, make_packs=lambda c: kept, make_preregs=lambda c: preregs,
                              make_experiments=lambda c: experiments, parts=frozenset())
    client = TestClient(app)
    pack_id = client.post("/packs", files={"file": ("p.zip", zipped(files()), "application/zip")}, headers=FOUNDER).json()["pack"]["id"]
    draft = client.post("/preregistrations", json={"paper": "policies", "title": "Freshness", "hypotheses": [H1.ui()]}, headers=FOUNDER).json()
    return client, pack_id, draft["id"]


def body(pack_id: str, prereg_id: str, **change) -> dict:
    return {"paper": "policies", "packId": pack_id, "preregId": prereg_id, "conditions": ["C0", "C1"], "seeds": [1, 2], "budgetUsd": 1.0, **change}


def test_creating_names_every_problem_before_any_money_is_spent(monkeypatch):
    client, pack_id, prereg_id = lab_client(monkeypatch)
    unlocked = client.post("/experiments", json=body(pack_id, prereg_id), headers=FOUNDER)
    assert unlocked.status_code == 422 and "the preregistration must be locked first" in unlocked.json()["problems"]

    client.post(f"/preregistrations/{prereg_id}/lock", json={"confirm": "Freshness"}, headers=FOUNDER)
    problems = client.post("/experiments", json=body(pack_id, prereg_id, conditions=["C0", "C2"], budgetUsd=99, paper="security"), headers=FOUNDER).json()["problems"]
    assert any(p.startswith("C2: Delete and rebuild") for p in problems)
    assert "the preregistration compares C1, which this run leaves out" in problems
    assert "the cap is at most 40.0 dollars" in problems and "a freshness pack cannot run for the security paper yet" in problems

    options = client.get("/options", headers=FOUNDER).json()
    assert {c["code"]: c["available"] for c in options["conditions"]} == {"C0": True, "C1": True, "C3": True, "C2": False}


def test_a_run_starts_in_the_background_and_reads_back(monkeypatch):
    client, pack_id, prereg_id = lab_client(monkeypatch)
    client.post(f"/preregistrations/{prereg_id}/lock", json={"confirm": "Freshness"}, headers=FOUNDER)
    created = client.post("/experiments", json=body(pack_id, prereg_id), headers=FOUNDER)
    assert created.status_code == 201
    experiment = created.json()
    assert experiment["status"] == "estimated" and experiment["notes"]["estimate"]["cases"] == 16 and experiment["notes"]["estimate"]["usd"] > 0

    assert client.post(f"/experiments/{experiment['id']}/start", headers=FOUNDER).status_code == 202
    deadline = time.monotonic() + 20
    while client.get(f"/experiments/{experiment['id']}/progress", headers=FOUNDER).json()["status"] not in runner_terminal() and time.monotonic() < deadline:
        time.sleep(0.1)
    progress = client.get(f"/experiments/{experiment['id']}/progress", headers=FOUNDER).json()
    assert progress["status"] == "finished" and progress["done"] == progress["total"] == 16

    read = client.get(f"/experiments/{experiment['id']}/results", headers=FOUNDER).json()
    assert read["verdicts"][0]["hypothesisId"] == "H1" and {m["provenance"] for m in read["metrics"]} == {"lab"}
    one = client.get(f"/experiments/{experiment['id']}/cases", params={"condition": "C0", "failed": True}, headers=FOUNDER).json()
    assert one["total"] >= 1 and len(one["items"]) == 1 and one["items"][0]["outcome"]["label"] != "fresh"
    assert client.post(f"/experiments/{experiment['id']}/start", headers=FOUNDER).status_code == 409  # finished stays finished
    assert client.get("/experiments/nope", headers=FOUNDER).status_code == 404


def runner_terminal() -> set[str]:
    return {"finished", "failed", "invalid_run", "budget_reached"}
