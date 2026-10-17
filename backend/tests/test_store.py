# test_store.py: the same storage checks on memory and on Postgres, so both behave alike.
# Postgres tests are skipped when nothing answers on localhost:5433 (start it with backend/infra/compose.yaml).
# Uses: app/pipeline/store_postgres.py, app/pipeline/store_memory.py, app/pipeline/stages_intake.py, tests/golden.py.
import uuid

import pytest

from app.pipeline import fakes, stages_intake, stages_normalize
from app.pipeline.contracts_run import ApprovalRequest, RunRecord
from app.pipeline.store_memory import MemoryRecords
from app.pipeline.store_postgres import PostgresRecords, PostgresVault, connect, database_is_up
from tests.golden import NOW, golden, raw_sample

# Config
POSTGRES_UP = database_is_up()
NEEDS_POSTGRES = pytest.mark.skipif(not POSTGRES_UP, reason="no Postgres on localhost:5433")
RUN_S3 = RunRecord.model_validate(golden("s3", "RunRecord"))
RUN_S2 = RunRecord.model_validate(golden("s2", "RunRecord"))


# --- Helpers

@pytest.fixture(scope="module")
def connection():
    if not POSTGRES_UP:
        pytest.skip("no Postgres on localhost:5433")
    connection = connect()
    yield connection
    connection.close()


def fresh_tenant() -> str:
    """A new tenant per test, so tests never see each other's rows and need no cleanup."""
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture(params=["memory", "postgres"])
def vault(request):
    if request.param == "memory":
        return {}
    return PostgresVault(request.getfixturevalue("connection"), fresh_tenant())


@pytest.fixture(params=["memory", "postgres"])
def records(request):
    if request.param == "memory":
        return MemoryRecords(fresh_tenant())
    return PostgresRecords(request.getfixturevalue("connection"), fresh_tenant())


# --- Vault, on both

def test_vault_keeps_what_was_written(vault):
    vault["pii_tok_a"] = "Nimal Perera"
    vault["pii_tok_a"] = "Nimal Perera"  # S2 writes again on retry
    assert (vault["pii_tok_a"], len(vault), list(vault)) == ("Nimal Perera", 1, ["pii_tok_a"])


def test_vault_missing_token_raises(vault):
    with pytest.raises(KeyError):
        vault["pii_tok_missing"]


def test_s2_masks_into_the_vault(vault):
    store = {}
    k1 = stages_intake.capture(raw_sample("s2"), "finebase_labs", store, NOW)
    signal = stages_normalize.normalize(k1, "evt_raw", "finebase_labs", store, vault, set(), fakes.make_id_maker())
    assert {vault[token] for token in signal.pii_tokens} == {"Nimal Perera", "nimal.perera@example.lk", "+94 77 123 4567"}


# --- Records, on both

def test_saved_record_loads_back(records):
    approval = ApprovalRequest.model_validate(golden("s3", "ApprovalRequest"))
    records.save("approval", "apr_s3_0001", approval)
    assert ApprovalRequest.model_validate(records.load("approval", "apr_s3_0001")) == approval
    assert records.load("approval", "apr_missing") is None


def test_saving_again_adds_a_version(records):
    first = records.save("run", "run_s3", RUN_S3)
    second = records.save("run", "run_s3", RUN_S3.model_copy(update={"outcome": "resolved"}))
    assert (first, second) == (1, 2)
    assert [run["outcome"] for run in records.history("run", "run_s3")] == ["awaiting_approval", "resolved"]
    assert records.load("run", "run_s3")["outcome"] == "resolved"


def test_list_kind_gives_latest_of_each(records):
    records.save("run", "run_s2", RUN_S2)
    records.save("run", "run_s3", RUN_S3)
    records.save("run", "run_s3", RUN_S3.model_copy(update={"outcome": "resolved"}))
    assert [(run["run_id"], run["outcome"]) for run in records.list_kind("run")] == [("run_s2", "resolved"), ("run_s3", "resolved")]


# --- Postgres only

@NEEDS_POSTGRES
def test_vault_never_overwrites(connection):
    vault = PostgresVault(connection, fresh_tenant())
    vault["pii_tok_a"] = "first"
    vault["pii_tok_a"] = "second"
    assert vault["pii_tok_a"] == "first"


@NEEDS_POSTGRES
def test_tenants_never_see_each_other(connection):
    ours, theirs = PostgresVault(connection, fresh_tenant()), PostgresVault(connection, fresh_tenant())
    ours["pii_tok_a"] = "Nimal Perera"
    assert "pii_tok_a" not in theirs and len(theirs) == 0
