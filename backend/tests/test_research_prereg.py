# test_research_prereg.py: preregistrations (Research Lab step 5). A draft changes freely; locking needs the title typed
# back; a locked one never changes, through the API or straight in Postgres; of four people locking at once one wins; the
# hash catches any edit made around the API. Real Postgres when Docker is up; those rows are removed by switching the lock
# trigger off inside one test transaction, a path the product does not have.
# Uses: research/prereg.py, research/prereg_routes.py, research/routes.py, tests/test_research_api.py (people).
import threading
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.pipeline import store_postgres
from app.research import prereg, store
from app.research.contracts import Hypothesis
from app.research.routes import create_research_app
from tests.test_research_api import PEOPLE, FakeConnection

# Config
FOUNDER = {"x-persona": "h-founder"}
STALE = {"id": "H1", "metric": "stale_answer_rate", "comparator": "at_most", "threshold": -0.10, "conditions": ["C3", "C0"], "test": "exact_mcnemar"}
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")


def client_with(preregs) -> TestClient:
    return TestClient(create_research_app(connect=FakeConnection, people=PEOPLE, make_preregs=lambda connection: preregs))


def new_draft(client: TestClient, title: str = "Freshness", hypotheses: list | None = None):
    return client.post("/preregistrations", json={"paper": "policies", "title": title, "hypotheses": hypotheses or [STALE]}, headers=FOUNDER)


# --- Through the API

def test_a_draft_changes_then_locks_with_its_title_and_never_changes_again():
    client = client_with(prereg.MemoryPreregs())
    created = new_draft(client).json()
    edited = client.put(f"/preregistrations/{created['id']}", json={"title": "Freshness v2", "hypotheses": [{**STALE, "threshold": -0.12}]}, headers=FOUNDER)
    assert edited.status_code == 200 and edited.json()["sha256"] != created["sha256"]

    assert client.post(f"/preregistrations/{created['id']}/lock", json={"confirm": "Freshness"}, headers=FOUNDER).json() == {"error": "confirm_does_not_match_title"}
    locked = client.post(f"/preregistrations/{created['id']}/lock", json={"confirm": "Freshness v2"}, headers=FOUNDER).json()
    assert locked["lockedBy"] == "h-founder" and locked["sha256"] == edited.json()["sha256"]

    assert client.put(f"/preregistrations/{created['id']}", json={"title": "x", "hypotheses": [STALE]}, headers=FOUNDER).status_code == 409
    assert client.post(f"/preregistrations/{created['id']}/lock", json={"confirm": "Freshness v2"}, headers=FOUNDER).status_code == 409
    assert client.get(f"/preregistrations/{created['id']}", headers=FOUNDER).json()["hypotheses"][0]["threshold"] == -0.12


def test_bad_hypotheses_are_refused_with_every_problem_named():
    client = client_with(prereg.MemoryPreregs())
    bad = [{**STALE, "test": "vibes"}, {**STALE, "id": "H1", "alpha": 0.9, "conditions": []}]
    answer = new_draft(client, hypotheses=bad)
    assert answer.status_code == 422 and len(answer.json()["problems"]) == 3
    assert new_draft(client, hypotheses=[STALE, STALE]).json()["problems"] == ["H1: used twice"]
    assert new_draft(client, title="  ").status_code == 422
    assert client.post("/preregistrations", json={"paper": "policies", "title": "t", "hypotheses": []}, headers=FOUNDER).json()["problems"] == ["at least one hypothesis is needed"]


def test_only_the_founder_or_research_role_and_unknown_ids_are_404():
    client = client_with(prereg.MemoryPreregs())
    assert new_draft(client).status_code == 201
    assert client.post("/preregistrations", json={"paper": "policies", "title": "t", "hypotheses": [STALE]}, headers={"x-persona": "h-steward"}).status_code == 403
    assert client.get("/preregistrations/nope", headers=FOUNDER).status_code == 404


def test_the_hash_catches_an_edit_made_around_the_api():
    written = prereg.draft("policies", "Freshness", [Hypothesis.model_validate(STALE)])
    assert prereg.holds(written)
    assert not prereg.holds(written.model_copy(update={"hypotheses": [Hypothesis.model_validate({**STALE, "threshold": -0.05})]}))


# --- Real Postgres

@pytest.fixture
def postgres_preregs():
    connection = store.connect()
    made: list[str] = []
    yield prereg.PostgresPreregs(connection), made
    with psycopg.connect(store_postgres.DATABASE_URL) as cleanup, cleanup.transaction():
        cleanup.execute("ALTER TABLE research.preregistrations DISABLE TRIGGER prereg_locked")  # undone with the transaction's end
        cleanup.execute("DELETE FROM research.preregistrations WHERE id = ANY(%s::uuid[])", (made,))
        cleanup.execute("ALTER TABLE research.preregistrations ENABLE TRIGGER prereg_locked")


@NEEDS_POSTGRES
def test_on_postgres_four_people_lock_at_once_and_one_wins(postgres_preregs):
    preregs, made = postgres_preregs
    created = preregs.create(prereg.draft("policies", f"Race {uuid.uuid4()}", [Hypothesis.model_validate(STALE)]))
    made.append(created.id)
    outcomes: list[str] = []

    def lock(person: str) -> None:
        with store.connect() as own:
            try:
                prereg.PostgresPreregs(own).lock(created.id, person)
                outcomes.append(person)
            except prereg.PreregLocked:
                outcomes.append("refused")

    workers = [threading.Thread(target=lock, args=(f"h-{i}",)) for i in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    winner = [o for o in outcomes if o != "refused"]
    assert len(winner) == 1 and outcomes.count("refused") == 3
    assert preregs.get(created.id).locked_by == winner[0] and prereg.holds(preregs.get(created.id))


@NEEDS_POSTGRES
def test_on_postgres_a_locked_row_refuses_every_change_even_outside_the_api(postgres_preregs):
    preregs, made = postgres_preregs
    created = preregs.create(prereg.draft("policies", f"Locked {uuid.uuid4()}", [Hypothesis.model_validate(STALE)]))
    made.append(created.id)
    preregs.edit(created.id, created.title, [Hypothesis.model_validate({**STALE, "threshold": -0.2})])
    preregs.lock(created.id, "h-founder")
    with pytest.raises(prereg.PreregLocked):
        preregs.edit(created.id, "changed", [Hypothesis.model_validate(STALE)])
    with psycopg.connect(store_postgres.DATABASE_URL, autocommit=True) as direct, pytest.raises(psycopg.errors.CheckViolation):
        direct.execute("UPDATE research.preregistrations SET hypotheses = '[]' WHERE id = %s", (created.id,))
    assert preregs.get(created.id).hypotheses[0].threshold == -0.2
