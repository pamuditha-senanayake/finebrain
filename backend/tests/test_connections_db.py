# test_connections_db.py: a database connection on the real local Postgres. A read-only user passes and its tables are
# read; a user that can change data is refused; agent reads are one SELECT, read only, capped; writes never get through.
import json

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import conn_call, conn_db, fakes, orchestrate, store_postgres
from tests.golden import NOW

# Config
SEED, HQ = load_hq()
TENANT = SEED["tenant_id"]
FOUNDER = "h-pamuditha"
OWNER_URL = store_postgres.DATABASE_URL
READER_URL = OWNER_URL.replace("finebrain:finebrain@", "brain_reader_test:test-only-reader@")
SETUP = """
DROP SCHEMA IF EXISTS shop_test CASCADE; CREATE SCHEMA shop_test;
CREATE TABLE shop_test.orders (id text PRIMARY KEY, customer text, amount_minor int, status text);
INSERT INTO shop_test.orders VALUES ('ORD-1', 'amara', 4000, 'paid'), ('ORD-2', 'amara', 1900, 'paid');
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brain_reader_test') THEN
  CREATE ROLE brain_reader_test LOGIN PASSWORD 'test-only-reader' NOSUPERUSER NOCREATEDB NOCREATEROLE; END IF; END $$;
GRANT USAGE ON SCHEMA shop_test TO brain_reader_test; GRANT SELECT ON ALL TABLES IN SCHEMA shop_test TO brain_reader_test;
"""

pytestmark = pytest.mark.skipif(not store_postgres.database_is_up(), reason="Postgres is not running")


def answer(url: str) -> str:
    block = {"database": {"engine": "postgres", "schemas": ["shop_test"], "notes": "orders of the shop"}, "database_url": url}
    return f"Created the user.\n```brain-connection\n{json.dumps(block)}\n```"


@pytest.fixture
def desk():
    with psycopg.connect(OWNER_URL, autocommit=True) as db:
        db.execute(SETUP)
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    client = TestClient(create_api_app(lane, HQ))
    created = client.post(f"/api/t/{TENANT}/connections", json={"name": "Orders database", "kind": "database", "platform": "Shop"}, headers={"x-persona": FOUNDER})
    yield client, lane, created.json()["id"]
    with psycopg.connect(OWNER_URL, autocommit=True) as db:
        db.execute("DROP SCHEMA IF EXISTS shop_test CASCADE")


def deliver_and_test(client, connection_id: str, url: str) -> dict:
    headers = {"x-persona": FOUNDER}
    client.post(f"/api/t/{TENANT}/connections/{connection_id}/deliver", json={"answer": answer(url)}, headers=headers)
    return client.post(f"/api/t/{TENANT}/connections/{connection_id}/test", json={}, headers=headers).json()


def test_read_only_user_passes_and_its_tables_are_read(desk):
    client, lane, connection_id = desk
    tested = deliver_and_test(client, connection_id, READER_URL)
    assert tested["status"] == "tested" and tested["platform"] == "Shop" and tested["kind"] == "database", tested["tests"]
    assert tested["tables"] == ["shop_test.orders"] and READER_URL not in json.dumps(tested)
    rows = conn_db.read(lane, conn_call.load(lane, connection_id), "SELECT id, amount_minor FROM shop_test.orders WHERE customer = %s ORDER BY id", ("amara",))
    assert rows == [{"id": "ORD-1", "amount_minor": 4000}, {"id": "ORD-2", "amount_minor": 1900}]


def test_a_user_that_can_change_data_is_refused(desk):
    client, _, connection_id = desk
    tested = deliver_and_test(client, connection_id, OWNER_URL)
    read_only = {line["item"]: line for line in tested["tests"]}["Read only"]
    assert read_only["ok"] is False and "read-only user" in read_only["detail"] and tested["status"] == "delivered"


@pytest.mark.parametrize("sql", ["DELETE FROM shop_test.orders", "SELECT 1; DROP TABLE shop_test.orders", "UPDATE shop_test.orders SET status = 'x'",
                                 "WITH gone AS (DELETE FROM shop_test.orders RETURNING *) SELECT * FROM gone"])
def test_writes_never_get_through(desk, sql):
    client, lane, connection_id = desk
    deliver_and_test(client, connection_id, READER_URL)
    with pytest.raises(conn_db.NotAllowed):
        conn_db.read(lane, conn_call.load(lane, connection_id), sql)
    with psycopg.connect(OWNER_URL) as db:
        assert db.execute("SELECT count(*) FROM shop_test.orders").fetchone()[0] == 2


def test_the_server_refuses_writes_even_past_the_check(desk):
    """The read-only transaction is the real wall: a write hidden from the word check still fails at the server."""
    client, lane, connection_id = desk
    deliver_and_test(client, connection_id, OWNER_URL)  # even the owner, through the brain's door
    with conn_db.open_read_only(lane, conn_call.load(lane, connection_id)) as db, pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        db.execute("INSERT INTO shop_test.orders VALUES ('ORD-3', 'x', 1, 'paid')")
