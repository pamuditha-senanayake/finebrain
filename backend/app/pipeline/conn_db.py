# conn_db.py: the brain's only door into a connected database, built so an agent can never change or delete data.
# The test proves the user is read only (no write rights on any table, no superuser, no role or database creation) and
# reads the schema; every query is one SELECT, inside a read-only transaction, with a time limit and a row cap.
# Used by: conn_test.py, agent tools. Uses: conn_call.py (secret), psycopg.
import re

import psycopg

from app.pipeline.conn_call import Connection, get_secret

# Config
CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MS = 5000
ROW_LIMIT = 200
READ_ONLY_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
WRITE_WORDS = re.compile(r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant|revoke|copy|call|do|vacuum|lock|set|reset)\b", re.IGNORECASE)
WRITE_RIGHTS = "INSERT,UPDATE,DELETE,TRUNCATE"
TABLES_SQL = """SELECT c.table_schema, c.table_name, string_agg(c.column_name || ' ' || c.data_type, ', ' ORDER BY c.ordinal_position)
FROM information_schema.columns c WHERE c.table_schema = ANY(%s) GROUP BY 1, 2 ORDER BY 1, 2"""
WRITABLE_SQL = """SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname = ANY(%s)
AND (has_table_privilege(quote_ident(schemaname) || '.' || quote_ident(tablename), %s))"""
ROLE_SQL = "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = current_user"


class NotAllowed(Exception):
    """A query the guard refuses before it reaches the database."""


def open_read_only(lane, connection: Connection) -> psycopg.Connection:
    """A connection that refuses writes at the server, whatever is sent."""
    url = get_secret(lane, connection.connection_id, "database_url")
    if not url:
        raise NotAllowed("No database address yet")
    # Set at connect time, so even the first transaction is read only (a SET after connecting only reaches the next one)
    options = f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}"
    return psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS, autocommit=False, options=options)


# --- What the test checks

def write_risks(db: psycopg.Connection, schemas: list[str]) -> list[str]:
    """Every way this user could change data. Empty means read only."""
    superuser, create_role, create_db, bypass_rls = db.execute(ROLE_SQL).fetchone()
    risks = [name for name, has in (("superuser", superuser), ("can create roles", create_role), ("can create databases", create_db), ("ignores row security", bypass_rls)) if has]
    writable = [row[0] for row in db.execute(WRITABLE_SQL, (schemas, WRITE_RIGHTS)).fetchall()]
    return risks + ([f"can change {len(writable)} tables, e.g. {writable[0]}"] if writable else [])


def read_schema(db: psycopg.Connection, spec) -> list[dict]:
    """The tables the brain may read, with their columns, limited to the named tables when there are any."""
    rows = db.execute(TABLES_SQL, (spec.schemas,)).fetchall()
    shown = [{"table": f"{schema}.{table}", "columns": columns} for schema, table, columns in rows]
    return [t for t in shown if not spec.tables or t["table"] in spec.tables]


# --- Agent reads

def check_query(sql: str) -> None:
    """One SELECT, nothing that writes. The read-only transaction is the real wall; this keeps mistakes out early."""
    body = sql.strip().rstrip(";")
    if ";" in body:
        raise NotAllowed("One statement at a time")
    if not READ_ONLY_START.match(body) or WRITE_WORDS.search(body):
        raise NotAllowed("Only reading is allowed")


def read(lane, connection: Connection, sql: str, params: tuple = ()) -> list[dict]:
    """Run one checked SELECT and return at most ROW_LIMIT rows. The transaction is always rolled back."""
    check_query(sql)
    with open_read_only(lane, connection) as db:
        cursor = db.execute(f"SELECT * FROM ({sql.strip().rstrip(';')}) AS brain_read LIMIT {ROW_LIMIT}", params)
        names = [column.name for column in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
        db.rollback()
    return rows
