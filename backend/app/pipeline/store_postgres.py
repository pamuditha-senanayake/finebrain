# store_postgres.py: Postgres storage for Lane A: the PII vault (S2) and append-only records (S8, S9, S10).
# Used by: tests/test_store.py, orchestrate.py from step 6. Uses: nothing local.
# Vault values are encrypted at rest with pgcrypto. Graph, facts, chunks and the outbox come later.
import os
from collections.abc import Iterator, MutableMapping

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel

# Config
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://finebrain:finebrain@localhost:5433/finebrain")
VAULT_KEY = os.environ.get("VAULT_KEY", "dev-only-vault-key")  # production key comes from Secrets Manager + KMS
SCHEMA = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS pii_vault (
    tenant_id       text        NOT NULL,
    token           text        NOT NULL,
    value           text,
    value_encrypted bytea,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, token)
);
ALTER TABLE pii_vault ADD COLUMN IF NOT EXISTS value_encrypted bytea;
ALTER TABLE pii_vault ALTER COLUMN value DROP NOT NULL;
CREATE TABLE IF NOT EXISTS records (
    tenant_id   text        NOT NULL,
    kind        text        NOT NULL,
    record_id   text        NOT NULL,
    version     int         NOT NULL,
    body        jsonb       NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, kind, record_id, version)
);
"""


# --- Connection

def connect(url: str = DATABASE_URL) -> psycopg.Connection:
    """Open a connection and make sure the tables exist."""
    connection = psycopg.connect(url, autocommit=True, connect_timeout=3)
    connection.execute(SCHEMA)
    return connection


def database_is_up(url: str = DATABASE_URL) -> bool:
    """True when Postgres answers, so tests can skip cleanly when Docker is down."""
    try:
        psycopg.connect(url, connect_timeout=2).close()
    except psycopg.OperationalError:
        return False
    return True


# --- PII vault (S2)

class PostgresVault(MutableMapping[str, str]):
    """Behaves like the dict S2 writes to, so the stage does not change when this is swapped in."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id

    def __getitem__(self, token: str) -> str:
        # value is only set on rows written before encryption; new rows hold value_encrypted alone
        row = self.connection.execute(
            "SELECT coalesce(pgp_sym_decrypt(value_encrypted, %s), value) FROM pii_vault WHERE tenant_id = %s AND token = %s",
            (VAULT_KEY, self.tenant_id, token),
        ).fetchone()
        if row is None:
            raise KeyError(token)
        return row[0]

    def __setitem__(self, token: str, value: str) -> None:
        # Same value always gives the same token, so a second write is a no-op, never an overwrite
        self.connection.execute(
            "INSERT INTO pii_vault (tenant_id, token, value_encrypted) VALUES (%s, %s, pgp_sym_encrypt(%s, %s)) ON CONFLICT DO NOTHING",
            (self.tenant_id, token, value, VAULT_KEY),
        )

    def __delitem__(self, token: str) -> None:
        """Only for a personal data deletion request."""
        self.connection.execute("DELETE FROM pii_vault WHERE tenant_id = %s AND token = %s", (self.tenant_id, token))

    def __iter__(self) -> Iterator[str]:
        rows = self.connection.execute("SELECT token FROM pii_vault WHERE tenant_id = %s ORDER BY created_at", (self.tenant_id,))
        return iter([row[0] for row in rows])

    def __len__(self) -> int:
        return self.connection.execute("SELECT count(*) FROM pii_vault WHERE tenant_id = %s", (self.tenant_id,)).fetchone()[0]


# --- Records (S8 approvals, S9 actions, S10 runs)

class PostgresRecords:
    """Append-only: saving the same id again adds a version, so nothing is overwritten."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id

    def save(self, kind: str, record_id: str, body: BaseModel) -> int:
        """Store a new version and return its number."""
        row = self.connection.execute(
            """INSERT INTO records (tenant_id, kind, record_id, version, body)
               SELECT %(tenant)s, %(kind)s, %(id)s, COALESCE(MAX(version), 0) + 1, %(body)s
               FROM records WHERE tenant_id = %(tenant)s AND kind = %(kind)s AND record_id = %(id)s
               RETURNING version""",
            {"tenant": self.tenant_id, "kind": kind, "id": record_id, "body": Jsonb(body.model_dump(mode="json"))},
        ).fetchone()
        return row[0]

    def load(self, kind: str, record_id: str) -> dict | None:
        """The latest version, or None when there is none."""
        history = self.history(kind, record_id)
        return history[-1] if history else None

    def history(self, kind: str, record_id: str) -> list[dict]:
        """Every version, oldest first."""
        rows = self.connection.execute(
            "SELECT body FROM records WHERE tenant_id = %s AND kind = %s AND record_id = %s ORDER BY version",
            (self.tenant_id, kind, record_id),
        )
        return [row[0] for row in rows]

    def list_kind(self, kind: str) -> list[dict]:
        """The latest version of every record of one kind."""
        rows = self.connection.execute(
            """SELECT DISTINCT ON (record_id) body FROM records
               WHERE tenant_id = %s AND kind = %s ORDER BY record_id, version DESC""",
            (self.tenant_id, kind),
        )
        return [row[0] for row in rows]

    def purge(self, kind: str, record_id: str) -> list[dict]:
        """Erase every version of one record and return what it held, so the caller can save a scrubbed copy."""
        history = self.history(kind, record_id)
        self.connection.execute("DELETE FROM records WHERE tenant_id = %s AND kind = %s AND record_id = %s", (self.tenant_id, kind, record_id))
        return history
