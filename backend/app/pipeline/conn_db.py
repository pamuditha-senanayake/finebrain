# conn_db.py: the brain's only doors into a connected database. The read door is built so an agent can never change or
# delete data: the test proves the user is read only and reads the schema; every query is one SELECT, inside a read-only
# transaction, with a time limit and a row cap. The refund door signs in as a second user, which the test proves may only
# add a refund and set an order's status, nothing more. Used by: conn_test.py, tools_read.py, tools_write.py.
# Uses: conn_call.py (secret), psycopg.
import re

import psycopg

from app.pipeline.conn_call import Connection, get_secret

# Config
CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MS = 5000
LOCK_TIMEOUT_MS = 3000  # a refund waits this long for another worker's lock on the same order, then retries
ROW_LIMIT = 200
READ_ONLY_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
WRITE_WORDS = re.compile(r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant|revoke|copy|call|do|vacuum|lock|set|reset)\b", re.IGNORECASE)
WRITE_RIGHTS = "INSERT,UPDATE,DELETE,TRUNCATE"
TABLES_SQL = """SELECT c.table_schema, c.table_name, string_agg(c.column_name || ' ' || c.data_type, ', ' ORDER BY c.ordinal_position)
FROM information_schema.columns c WHERE c.table_schema = ANY(%s) GROUP BY 1, 2 ORDER BY 1, 2"""
WRITABLE_SQL = """SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname = ANY(%s)
AND (has_table_privilege(quote_ident(schemaname) || '.' || quote_ident(tablename), %s)
  OR has_any_column_privilege(quote_ident(schemaname) || '.' || quote_ident(tablename), 'INSERT,UPDATE'))"""
COLUMN_RIGHTS_SQL = """SELECT c.table_schema || '.' || c.table_name, c.column_name, r.name FROM information_schema.columns c
CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE']) AS r(name) WHERE c.table_schema = ANY(%s)
AND has_column_privilege(quote_ident(c.table_schema) || '.' || quote_ident(c.table_name), c.column_name, r.name)"""
REMOVE_RIGHTS_SQL = """SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname = ANY(%s)
AND has_table_privilege(quote_ident(schemaname) || '.' || quote_ident(tablename), 'DELETE,TRUNCATE')"""
ROLE_SQL = "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = current_user"


class NotAllowed(Exception):
    """A query the guard refuses before it reaches the database."""


def open_refunds(lane, connection: Connection) -> psycopg.Connection:
    """The refund user's connection: one transaction per refund, with time limits so a stuck lock never hangs S9."""
    url = get_secret(lane, connection.connection_id, "refund_database_url")
    if not url:
        raise NotAllowed("No refund user yet")
    options = f"-c statement_timeout={STATEMENT_TIMEOUT_MS} -c lock_timeout={LOCK_TIMEOUT_MS}"
    return psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS, autocommit=False, options=options)


def open_read_only(lane, connection: Connection) -> psycopg.Connection:
    """A connection that refuses writes at the server, whatever is sent."""
    url = get_secret(lane, connection.connection_id, "database_url")
    if not url:
        raise NotAllowed("No database address yet")
    # Set at connect time, so even the first transaction is read only (a SET after connecting only reaches the next one)
    options = f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}"
    return psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS, autocommit=False, options=options)


# --- What the test checks

def role_risks(db: psycopg.Connection) -> list[str]:
    """Powers over the whole server that no brain user may have."""
    superuser, create_role, create_db, bypass_rls = db.execute(ROLE_SQL).fetchone()
    return [name for name, has in (("superuser", superuser), ("can create roles", create_role), ("can create databases", create_db), ("ignores row security", bypass_rls)) if has]


def write_risks(db: psycopg.Connection, schemas: list[str]) -> list[str]:
    """Every way this user could change data, a single column included. Empty means read only."""
    risks = role_risks(db)
    writable = [row[0] for row in db.execute(WRITABLE_SQL, (schemas, WRITE_RIGHTS)).fetchall()]
    return risks + ([f"can change {len(writable)} tables, e.g. {writable[0]}"] if writable else [])


def refund_risks(db: psycopg.Connection, schemas: list[str], m) -> list[str]:
    """Every right the refund user has beyond adding a refund and setting an order's status, or lacks for them. Empty is exactly right."""
    risks = role_risks(db)
    allowed = lambda table, column, right: (right == "INSERT" and table == m.refunds) or (right == "UPDATE" and (table, column) == (m.orders, m.status))
    rights = db.execute(COLUMN_RIGHTS_SQL, (schemas,)).fetchall()
    extra = sorted({f"{right.lower()} {table}.{column}" for table, column, right in rights if not allowed(table, column, right)})
    removes = [row[0] for row in db.execute(REMOVE_RIGHTS_SQL, (schemas,)).fetchall()]
    has = {(table, column, right) for table, column, right in rights}
    missing = [] if (m.orders, m.status, "UPDATE") in has and any(t == m.refunds and r == "INSERT" for t, _, r in has) else ["cannot add a refund and set the order's status"]
    return risks + missing + ([f"can also {extra[0]}" + (f" and {len(extra) - 1} more" if len(extra) > 1 else "")] if extra else []) + ([f"can delete from {removes[0]}"] if removes else [])


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
