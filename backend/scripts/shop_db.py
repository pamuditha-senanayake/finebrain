# shop_db.py: builds the Finebase Labs shop as its own Postgres database (finebase_shop) on the local server, from
# samples/shop_world.json, with a read-only user the brain connects as and a refund user that may only add refunds and set
# an order's status. S5 reads and S9 refunds through conn_db.py, exactly as on a customer's real database.
# Run from backend/:  uv run python scripts/shop_db.py
# Used by: tests/test_s5_*.py, tests/test_s9_real.py, scripts/s5_volume.py, scripts/s9_volume.py. Uses: store_postgres.py, psycopg.
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, ".")
from app.pipeline import store_postgres

# Config
SHOP_DB = "finebase_shop"
OWNER_URL = store_postgres.DATABASE_URL  # the local server's owner, who may create databases
READER, READER_PASSWORD = "brain_shop_reader", "test-only-shop-reader"
REFUNDER, REFUNDER_PASSWORD = "brain_shop_refunder", "test-only-shop-refunder"
WORLD = json.loads((Path(__file__).resolve().parents[1] / "samples" / "shop_world.json").read_text())
SCHEMA = """
DROP SCHEMA IF EXISTS shop CASCADE; CREATE SCHEMA shop;
CREATE TABLE shop.customers (id text PRIMARY KEY, email text UNIQUE NOT NULL, name text NOT NULL);
CREATE TABLE shop.orders (id text PRIMARY KEY, customer_id text NOT NULL REFERENCES shop.customers(id), product text NOT NULL,
  total_minor bigint NOT NULL, currency text NOT NULL, status text NOT NULL, paid_at timestamptz NOT NULL, payment_ref text UNIQUE NOT NULL);
CREATE INDEX orders_by_customer ON shop.orders (customer_id, paid_at DESC);
CREATE TABLE shop.refunds (id text PRIMARY KEY, order_id text NOT NULL REFERENCES shop.orders(id), amount_minor bigint NOT NULL,
  status text NOT NULL, created_at timestamptz NOT NULL);
CREATE INDEX refunds_by_order ON shop.refunds (order_id);
"""
READER_ROLE = f"""
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{READER}') THEN
  CREATE ROLE {READER} LOGIN PASSWORD '{READER_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE; END IF; END $$;
GRANT CONNECT ON DATABASE {SHOP_DB} TO {READER}; GRANT USAGE ON SCHEMA shop TO {READER};
GRANT SELECT ON ALL TABLES IN SCHEMA shop TO {READER};
"""
REFUNDER_ROLE = f"""
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{REFUNDER}') THEN
  CREATE ROLE {REFUNDER} LOGIN PASSWORD '{REFUNDER_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; END $$;
ALTER ROLE {REFUNDER} SET statement_timeout = '5s';
GRANT CONNECT ON DATABASE {SHOP_DB} TO {REFUNDER}; GRANT USAGE ON SCHEMA shop TO {REFUNDER};
GRANT SELECT ON shop.customers, shop.orders, shop.refunds TO {REFUNDER};
GRANT INSERT ON shop.refunds TO {REFUNDER};
GRANT UPDATE (status) ON shop.orders TO {REFUNDER};
"""


def url_for(database: str, user: str = "finebrain:finebrain") -> str:
    """The local server's address for one database and user."""
    base = OWNER_URL.rsplit("/", 1)[0].replace("finebrain:finebrain@", f"{user}@")
    return f"{base}/{database}"


def reader_url() -> str:
    """What the shop hands the brain: a user that can only read."""
    return url_for(SHOP_DB, f"{READER}:{READER_PASSWORD}")


def refunder_url() -> str:
    """What the shop hands the brain for refunds: a user that may only add a refund and set an order's status."""
    return url_for(SHOP_DB, f"{REFUNDER}:{REFUNDER_PASSWORD}")


def owner_url() -> str:
    """The shop's own address, for tests that change the shop the way its staff would."""
    return url_for(SHOP_DB)


def create_database() -> None:
    """The shop's database, apart from the brain's own, created once."""
    with psycopg.connect(OWNER_URL, autocommit=True) as server:
        if not server.execute("SELECT 1 FROM pg_database WHERE datname = %s", (SHOP_DB,)).fetchone():
            server.execute(f"CREATE DATABASE {SHOP_DB}")


def load_world(world: dict = WORLD) -> None:
    """Fresh tables with the sample customers, orders and refunds, and the read-only user."""
    with psycopg.connect(owner_url(), autocommit=True) as shop:
        shop.execute(SCHEMA)
        for table, columns in (("customers", ("id", "email", "name")), ("orders", ("id", "customer_id", "product", "total_minor", "currency", "status", "paid_at", "payment_ref")),
                               ("refunds", ("id", "order_id", "amount_minor", "status", "created_at"))):
            rows = [tuple(row[column] for column in columns) for row in world[table]]
            with shop.cursor() as cursor:
                cursor.executemany(f"INSERT INTO shop.{table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})", rows)
        shop.execute(READER_ROLE)
        shop.execute(REFUNDER_ROLE)


def setup(world: dict = WORLD) -> str:
    """Build the shop and return the reader's address."""
    create_database()
    load_world(world)
    return reader_url()


if __name__ == "__main__":
    print(f"shop ready: {SHOP_DB}, read-only user {READER}, refund user {REFUNDER}")
    setup()
