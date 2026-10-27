# test_research_schema.py: the research schema on real Postgres (Research Lab step 1). It lives apart from every product
# table, two workers can create it at once, a locked preregistration never changes, and bad rows are refused.
# Every row a test writes is rolled back. Skipped when Docker is off. Uses: app/research/store.py.
import threading
import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.pipeline import store_postgres
from app.research import store

NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")
pytestmark = NEEDS_POSTGRES


def public_tables(connection: psycopg.Connection) -> set[str]:
    rows = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    return {name for (name,) in rows}


def research_tables(connection: psycopg.Connection) -> set[str]:
    rows = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'research'")
    return {name for (name,) in rows}


def draft_prereg(connection: psycopg.Connection) -> str:
    prereg_id = str(uuid.uuid4())
    connection.execute("INSERT INTO research.preregistrations (id, paper, title, hypotheses, sha256) VALUES (%s, 'policies', 'Freshness', %s, 'abc')",
                       (prereg_id, Jsonb([{"id": "H1", "metric": "stale_answer_rate"}])))
    return prereg_id


def new_experiment(connection: psycopg.Connection) -> str:
    experiment_id = str(uuid.uuid4())
    connection.execute(
        """INSERT INTO research.experiments (id, paper, source, conditions, seeds, trials, models, budget_usd, config_sha256, git_commit, status)
           VALUES (%s, 'policies', 'lab', ARRAY['C0', 'C3'], ARRAY[1, 2, 3], 1, %s, 5, 'cfg', 'a7bc601', 'draft')""", (experiment_id, Jsonb({})))
    return experiment_id


# --- The schema

def test_the_schema_is_made_once_and_touches_no_product_table():
    with psycopg.connect(store_postgres.DATABASE_URL, autocommit=True) as connection:
        before = public_tables(connection)
        store.ensure_schema(connection)
        store.ensure_schema(connection)  # a restart changes nothing
        assert store.schema_ready(connection)
        assert public_tables(connection) == before
        assert research_tables(connection) == set(store.TABLES)


def test_two_workers_create_the_schema_at_the_same_time():
    errors: list[Exception] = []

    def start_worker() -> None:
        try:
            store.connect().close()
        except Exception as error:  # collected, so the test names it instead of a thread swallowing it
            errors.append(error)

    workers = [threading.Thread(target=start_worker) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert errors == []


# --- Preregistration lock

def test_a_draft_can_change_and_a_locked_preregistration_never_can():
    store.connect().close()
    with psycopg.connect(store_postgres.DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        # Step 1: a draft is edited, then locked
        prereg_id = draft_prereg(connection)
        connection.execute("UPDATE research.preregistrations SET title = 'Freshness v2' WHERE id = %s", (prereg_id,))
        connection.execute("UPDATE research.preregistrations SET locked_at = now(), locked_by = 'h-pamuditha', sha256 = 'def' WHERE id = %s", (prereg_id,))

        # Step 2: no edit, unlock or delete gets through
        for statement in ["UPDATE research.preregistrations SET hypotheses = '[]' WHERE id = %s",
                          "UPDATE research.preregistrations SET locked_at = NULL, locked_by = NULL WHERE id = %s",
                          "DELETE FROM research.preregistrations WHERE id = %s"]:
            with pytest.raises(psycopg.errors.CheckViolation, match="preregistration_locked"), connection.transaction():
                connection.execute(statement, (prereg_id,))
        row = connection.execute("SELECT title, sha256 FROM research.preregistrations WHERE id = %s", (prereg_id,)).fetchone()
        assert row == ("Freshness v2", "def")


def test_a_lock_names_who_locked_it():
    store.connect().close()
    with psycopg.connect(store_postgres.DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        prereg_id = draft_prereg(connection)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute("UPDATE research.preregistrations SET locked_at = now() WHERE id = %s", (prereg_id,))


# --- Bad rows and teardown

def test_bad_values_are_refused():
    store.connect().close()
    with psycopg.connect(store_postgres.DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        experiment_id = new_experiment(connection)
        bad_rows = [
            ("INSERT INTO research.metric_values (experiment_id, metric_key, condition, value, provenance) VALUES (%s, 'm', 'C0', 0.1, 'made_up')", (experiment_id,)),
            ("INSERT INTO research.comparisons (experiment_id, hypothesis_id, metric_key, condition_a, condition_b, verdict) VALUES (%s, 'H1', 'm', 'C3', 'C1', 'maybe')", (experiment_id,)),
            ("INSERT INTO research.packs (id, kind, name, version, sha256, manifest, audit, uploaded_by) VALUES (%s, 'poetry', 'p', '1', 'x', '{}', '{}', 'h')", (str(uuid.uuid4()),)),
        ]
        for statement, values in bad_rows:
            with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(statement, values)


def test_a_case_result_is_written_once_and_goes_with_its_experiment():
    store.connect().close()
    with psycopg.connect(store_postgres.DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        experiment_id = new_experiment(connection)
        insert = "INSERT INTO research.case_results (experiment_id, condition, seed, trial, case_id, outcome) VALUES (%s, 'C3', 1, 1, 'q1', '{}')"
        connection.execute(insert, (experiment_id,))
        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute(insert, (experiment_id,))  # a resumed run cannot count a case twice

        connection.execute("DELETE FROM research.experiments WHERE id = %s", (experiment_id,))
        left = connection.execute("SELECT count(*) FROM research.case_results WHERE experiment_id = %s", (experiment_id,)).fetchone()[0]
        assert left == 0
