# audit.py: the append-only, hash-chained audit log. Each entry holds the previous entry's hash, so editing or
# deleting any entry breaks the chain, and verify_chain says where. Postgres and an in-memory twin.
# Used by: adapters.py, orchestrate.py (audit writer), tests. Uses: nothing local.
import hashlib
import json

import psycopg
from psycopg.types.json import Jsonb

# Config
GENESIS_HASH = "0" * 64
AUDITED_TOPICS = ["approvals.requested", "approvals.decided", "actions.executed", "runs.completed", "access.decisions"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    tenant_id   text        NOT NULL,
    seq         bigint      NOT NULL,
    event_id    text        NOT NULL,
    topic       text        NOT NULL,
    body        jsonb       NOT NULL,
    prev_hash   text        NOT NULL,
    hash        text        NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, seq),
    UNIQUE (tenant_id, event_id)
);
"""


def chain_hash(prev_hash: str, seq: int, event_id: str, topic: str, body: dict) -> str:
    """SHA-256 over the previous hash and this entry's canonical JSON."""
    canonical = json.dumps({"seq": seq, "event_id": event_id, "topic": topic, "body": body}, sort_keys=True, default=str)
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def verify_chain(entries: list[dict]) -> int | None:
    """The seq of the first entry that does not fit the chain, or None when the whole chain holds."""
    prev_hash = GENESIS_HASH
    for entry in entries:
        expected = chain_hash(prev_hash, entry["seq"], entry["event_id"], entry["topic"], entry["body"])
        if entry["prev_hash"] != prev_hash or entry["hash"] != expected:
            return entry["seq"]
        prev_hash = entry["hash"]
    return None


class MemoryAudit:
    def __init__(self):
        self.entries: list[dict] = []

    def append(self, event_id: str, topic: str, body: dict) -> bool:
        """Add one entry at the end of the chain. False when this event is already there."""
        if any(entry["event_id"] == event_id for entry in self.entries):
            return False
        seq, prev_hash = len(self.entries) + 1, self.entries[-1]["hash"] if self.entries else GENESIS_HASH
        self.entries.append({"seq": seq, "event_id": event_id, "topic": topic, "body": body, "prev_hash": prev_hash, "hash": chain_hash(prev_hash, seq, event_id, topic, body)})
        return True

    def in_order(self) -> list[dict]:
        return list(self.entries)


class PostgresAudit:
    """One row per entry. A per-tenant advisory lock keeps two writers from forking the chain."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection, self.tenant_id = connection, tenant_id
        connection.execute(SCHEMA)

    def append(self, event_id: str, topic: str, body: dict) -> bool:
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.tenant_id,))
            if self.connection.execute("SELECT 1 FROM audit_log WHERE tenant_id = %s AND event_id = %s", (self.tenant_id, event_id)).fetchone():
                return False
            last = self.connection.execute("SELECT seq, hash FROM audit_log WHERE tenant_id = %s ORDER BY seq DESC LIMIT 1", (self.tenant_id,)).fetchone()
            seq, prev_hash = (last[0] + 1, last[1]) if last else (1, GENESIS_HASH)
            self.connection.execute(
                "INSERT INTO audit_log (tenant_id, seq, event_id, topic, body, prev_hash, hash) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (self.tenant_id, seq, event_id, topic, Jsonb(body), prev_hash, chain_hash(prev_hash, seq, event_id, topic, body)),
            )
        return True

    def in_order(self) -> list[dict]:
        rows = self.connection.execute("SELECT seq, event_id, topic, body, prev_hash, hash FROM audit_log WHERE tenant_id = %s ORDER BY seq", (self.tenant_id,))
        return [dict(zip(("seq", "event_id", "topic", "body", "prev_hash", "hash"), row)) for row in rows]


def subscribe_audit(bus, audit) -> None:
    """The audit writer: one consumer group over every topic worth keeping for seven years."""
    for topic in AUDITED_TOPICS:
        bus.subscribe(topic, "audit", "S10", lambda envelope, topic=topic: audit.append(envelope.event_id, topic, audit_body(envelope)))


def audit_body(envelope) -> dict:
    """The payload plus the envelope details an auditor needs: when, who produced it, and which case it belongs to."""
    return {"payload": envelope.payload, "occurred_at": envelope.occurred_at.isoformat(), "producer": envelope.producer, "correlation_id": envelope.correlation_id}
