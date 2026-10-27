# lab_shop.py: a lab tenant's own shop, so S5 reads orders and S7 reads payments at decision time exactly as in production.
# One schema per lab in its own database (research_lab_shop), never the shop tests use, with a read-only user per lab
# that can see only that schema. Dropped, user and all, at teardown.
# Used by: research/lab_tenant.py. Uses: store_postgres.py (server address), conn_spec.py (OrderMap).
import secrets

import psycopg

from app.pipeline.conn_spec import OrderMap
from app.pipeline.store_postgres import DATABASE_URL

# Config
LAB_SHOP_DB = "research_lab_shop"
SERVER_URL = DATABASE_URL  # the local server's owner, who may create databases and roles
COLUMNS = {"customers": ("id", "email", "name"),
           "orders": ("id", "customer_id", "product", "total_minor", "currency", "status", "paid_at", "payment_ref"),
           "refunds": ("id", "order_id", "amount_minor", "status", "created_at")}
TABLES = """
CREATE SCHEMA IF NOT EXISTS {schema};
CREATE TABLE IF NOT EXISTS {schema}.customers (id text PRIMARY KEY, email text UNIQUE NOT NULL, name text NOT NULL);
CREATE TABLE IF NOT EXISTS {schema}.orders (id text PRIMARY KEY, customer_id text NOT NULL REFERENCES {schema}.customers(id),
  product text NOT NULL, total_minor bigint NOT NULL, currency text NOT NULL, status text NOT NULL, paid_at timestamptz NOT NULL,
  payment_ref text UNIQUE NOT NULL);
CREATE INDEX IF NOT EXISTS orders_by_customer ON {schema}.orders (customer_id, paid_at DESC);
CREATE TABLE IF NOT EXISTS {schema}.refunds (id text PRIMARY KEY, order_id text NOT NULL REFERENCES {schema}.orders(id),
  amount_minor bigint NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS refunds_by_order ON {schema}.refunds (order_id);
"""


def server_url(database: str, user: str = "finebrain:finebrain") -> str:
    base = SERVER_URL.rsplit("/", 1)[0].replace("finebrain:finebrain@", f"{user}@")
    return f"{base}/{database}"


def order_map(schema: str) -> OrderMap:
    return OrderMap(customers=f"{schema}.customers", orders=f"{schema}.orders", refunds=f"{schema}.refunds")


# --- Building

def create_database() -> None:
    """The lab shops' own database, created once. Two labs starting together: the loser's duplicate is fine."""
    with psycopg.connect(SERVER_URL, autocommit=True) as server:
        if server.execute("SELECT 1 FROM pg_database WHERE datname = %s", (LAB_SHOP_DB,)).fetchone():
            return
        try:
            server.execute(f"CREATE DATABASE {LAB_SHOP_DB}")
        except psycopg.errors.DuplicateDatabase:
            pass


def create_reader(shop: psycopg.Connection, schema: str) -> str:
    """A login that may only read this lab's schema. Returns its address, with a fresh password each time."""
    password = secrets.token_hex(16)
    if not shop.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (schema,)).fetchone():
        shop.execute(f"CREATE ROLE {schema} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
    shop.execute(f"ALTER ROLE {schema} PASSWORD '{password}'")  # hex only, so it is safe inside the quotes
    shop.execute(f"GRANT CONNECT ON DATABASE {LAB_SHOP_DB} TO {schema}; GRANT USAGE ON SCHEMA {schema} TO {schema}")
    shop.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {schema}")
    return server_url(LAB_SHOP_DB, f"{schema}:{password}")


def load_rows(shop: psycopg.Connection, schema: str, world: dict) -> None:
    """The pack's customers, orders and refunds. Loading twice adds nothing."""
    for table, columns in COLUMNS.items():
        rows = [tuple(row[column] for column in columns) for row in world.get(table, [])]
        with shop.cursor() as cursor:
            cursor.executemany(f"INSERT INTO {schema}.{table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) ON CONFLICT DO NOTHING", rows)


def build_shop(schema: str, world: dict) -> str:
    """The lab's shop with the pack's rows. Returns the read-only address S5 and S7 use. `schema` is a checked lab id."""
    create_database()
    with psycopg.connect(server_url(LAB_SHOP_DB), autocommit=True) as shop, shop.transaction():
        shop.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (schema,))  # the same lab built twice at once: one after the other
        shop.execute(TABLES.format(schema=schema))
        load_rows(shop, schema, world)
        return create_reader(shop, schema)


# --- Teardown

def drop_shop(schema: str) -> None:
    """The schema, its rows and its user. Safe to run again after a crash halfway."""
    create_database()
    with psycopg.connect(server_url(LAB_SHOP_DB), autocommit=True) as shop:
        shop.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        if shop.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (schema,)).fetchone():
            shop.execute(f"DROP OWNED BY {schema}")  # its grants on the database go too
            shop.execute(f"DROP ROLE {schema}")


def shop_left(schema: str) -> int:
    """1 for the schema still there, 1 for its user: 0 means gone."""
    with psycopg.connect(SERVER_URL, autocommit=True) as server:
        if not server.execute("SELECT 1 FROM pg_database WHERE datname = %s", (LAB_SHOP_DB,)).fetchone():
            return 0
    with psycopg.connect(server_url(LAB_SHOP_DB), autocommit=True) as shop:
        schemas = shop.execute("SELECT count(*) FROM pg_namespace WHERE nspname = %s", (schema,)).fetchone()[0]
        roles = shop.execute("SELECT count(*) FROM pg_roles WHERE rolname = %s", (schema,)).fetchone()[0]
    return schemas + roles
