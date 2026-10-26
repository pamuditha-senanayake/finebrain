# connect_brief_db.py: the brief for connecting a database. It asks for a new user that can only read the schemas the
# brain needs, explains why, and says how to hand the address back. The brain checks the user really is read only.
# When a need changes data (a refund), it also asks for a second user that may only add a refund and set an order's status.
# Used by: connect_brief.py. Uses: conn_call.py.
import json

from app.pipeline.conn_call import Connection

# Config
EXAMPLE_SQL = """CREATE ROLE brain_reader LOGIN PASSWORD '<strong random password>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE brain_reader SET default_transaction_read_only = on;
ALTER ROLE brain_reader SET statement_timeout = '5s';
GRANT CONNECT ON DATABASE <database> TO brain_reader;
GRANT USAGE ON SCHEMA <schema> TO brain_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA <schema> TO brain_reader;   -- or only the tables listed above
-- No INSERT, UPDATE, DELETE, TRUNCATE, no ownership, no other schemas."""
REFUND_SQL = """CREATE ROLE brain_refunder LOGIN PASSWORD '<another strong random password>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE brain_refunder SET statement_timeout = '5s';
GRANT CONNECT ON DATABASE <database> TO brain_refunder;
GRANT USAGE ON SCHEMA <schema> TO brain_refunder;
GRANT SELECT ON <schema>.customers, <schema>.orders, <schema>.refunds TO brain_refunder;
GRANT INSERT ON <schema>.refunds TO brain_refunder;              -- add a refund
GRANT UPDATE (status) ON <schema>.orders TO brain_refunder;      -- set the order to refunded, and nothing else
-- No DELETE, no TRUNCATE, no other column, no other table."""


def writes(connection: Connection) -> bool:
    return any(need.writes for need in connection.needs)


def answer_example(connection: Connection) -> dict:
    refund = {"refund_database_url": "postgresql://brain_refunder:<password>@<host>:5432/<database>?sslmode=require"} if writes(connection) else {}
    return {
        "database": {"engine": "postgres", "schemas": ["<schema>"], "tables": ["<schema>.<table>, only if limited"],
                     "notes": "<what the main tables and columns mean, in plain words>"},
        "database_url": "postgresql://brain_reader:<password>@<host>:5432/<database>?sslmode=require", **refund,
    }


def refund_section(connection: Connection) -> str:
    """Only when a need changes data: a second user, with the least right a refund needs."""
    if not writes(connection):
        return ""
    return f"""
## A second user, only for refunds
The brain also files refunds. It does that as its own user, which may add a refund and set an order's status, nothing else.
The brain locks the order, checks the refund against what was paid, and writes both in one transaction. Each refund has an
id made from the brain's request, so a retry never refunds twice. Its test fails if this user can delete, change any other
column, or write to any other table.

```sql
{REFUND_SQL}
```
"""


def needs_lines(connection: Connection) -> str:
    return "\n".join(f"- {need.text}" for need in connection.needs) or "- (not described yet)"


def brief(connection: Connection, company: str) -> str:
    """The request for whoever runs the database. Safety comes first, in their words and in the checks."""
    return f"""# Request from {company}: read-only access to {connection.system or connection.name}

{company} runs a company brain, an AI system that works with its tools under rules and approvals.
Goal: {connection.goal or "(not described yet)"}

## What the brain needs to read
{needs_lines(connection)}

## Safety first: a new user that can only read
The brain must never be able to change or delete anything. Please create a separate database user for it:
- It can only SELECT, only in the schemas (or tables) above. Nothing else.
- No superuser, no owner of any table, no right to create roles, databases or tables.
- Read-only by default and a short statement time limit.
- Connections only over TLS, and from the brain's address only if you keep an allow-list.
- Leave out columns the brain does not need (passwords, card numbers, secrets), for example with a view.

For PostgreSQL that looks like:
```sql
{EXAMPLE_SQL}
```

The brain also protects itself: it only sends single SELECT statements, inside a read-only transaction, with a 5 second
limit and at most 200 rows. Its test fails if this user can insert, update, delete, truncate or is a superuser.
Today the brain reads PostgreSQL directly. For another database, expose an API instead and ask for an API connection.
{refund_section(connection)}
## Answer in exactly this format
Reply with one block like this, and nothing secret anywhere else:

```brain-connection
{json.dumps(answer_example(connection), indent=2)}
```

The person who asked will paste your whole answer into the brain. It keeps the address encrypted, proves the user is read
only, and reads the table and column names so its agents understand the data."""
