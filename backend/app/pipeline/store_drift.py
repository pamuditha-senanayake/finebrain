# store_drift.py: the living memory's drift flags (stage 6), each a K18 DriftFlag with its state and the history of how it
# got there. One subject has at most one open flag per kind: a second raise adds evidence, never a second flag, and two
# workers raising at once still make one (a unique index on open flags). Flags are read by id, by area, by state and by the
# change request that fixes them, never by listing everything. PostgresDrift and its twin.
# Used by: stages_memory_drift.py, stages_memory_flow.py, api/memory_fixes.py, tests/test_memory_drift.py. Uses: contracts_memory.py.
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from app.pipeline.contracts_memory import DriftFlag

# Config
MAX_EVIDENCE = 50  # enough traces to show the drift; the rest are in the pattern counts
SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_drift (
    tenant_id  text    NOT NULL,
    flag_id    text    NOT NULL,
    kind       text    NOT NULL,
    subject_id text    NOT NULL,
    area       text    NOT NULL,
    state      text    NOT NULL,
    cr_id      text,
    body       jsonb   NOT NULL,
    events     jsonb   NOT NULL DEFAULT '[]',
    PRIMARY KEY (tenant_id, flag_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS memory_drift_one_open ON memory_drift (tenant_id, kind, subject_id) WHERE state <> 'resolved';
CREATE INDEX IF NOT EXISTS memory_drift_state ON memory_drift (tenant_id, state);
CREATE INDEX IF NOT EXISTS memory_drift_area ON memory_drift (tenant_id, area);
CREATE INDEX IF NOT EXISTS memory_drift_cr ON memory_drift (tenant_id, cr_id);
"""


def event(state: str, at: datetime, note: str) -> dict:
    return {"state": state, "at": at.isoformat(), "note": note}


def with_evidence(flag: DriftFlag, more: DriftFlag) -> DriftFlag:
    """The open flag, with the new evidence added in front and the newest reading of the signal."""
    evidence = list(dict.fromkeys([*more.evidence_trace_ids, *flag.evidence_trace_ids]))[:MAX_EVIDENCE]
    return flag.model_copy(update={"evidence_trace_ids": evidence, "latest": more.latest})


class MemoryDrift:
    """The in-memory twin of PostgresDrift."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.flags: dict[str, DriftFlag] = {}
        self.events: dict[str, list[dict]] = {}

    def open_flag(self, kind: str, subject_id: str) -> DriftFlag | None:
        return next((f for f in self.flags.values() if f.kind == kind and f.subject.id == subject_id and f.state != "resolved"), None)

    def raise_flag(self, flag: DriftFlag) -> tuple[DriftFlag, bool]:
        """Keep a new flag, or add its evidence to the open one. True when the flag is new."""
        held = self.open_flag(flag.kind, flag.subject.id)
        if held:
            self.flags[held.flag_id] = with_evidence(held, flag)
            return self.flags[held.flag_id], False
        if flag.flag_id in self.flags:  # the same id was resolved before: a new drift keeps the old one as history
            flag = flag.model_copy(update={"flag_id": f"{flag.flag_id}-{flag.raised_at:%Y%m%d%H%M%S}"})
        self.flags[flag.flag_id] = flag
        self.events[flag.flag_id] = [event(flag.state, flag.raised_at, "raised")]
        return flag, True

    def move(self, flag: DriftFlag, at: datetime, note: str) -> DriftFlag:
        """Save a flag's new state (and fix, re-check or note) with one line of history."""
        self.flags[flag.flag_id] = flag
        self.events.setdefault(flag.flag_id, []).append(event(flag.state, at, note))
        return flag

    def get(self, flag_id: str) -> DriftFlag | None:
        return self.flags.get(flag_id)

    def history(self, flag_id: str) -> list[dict]:
        return list(self.events.get(flag_id, []))

    def in_state(self, state: str) -> list[DriftFlag]:
        return sorted((f for f in self.flags.values() if f.state == state), key=lambda f: f.flag_id)

    def in_area(self, area: str) -> list[DriftFlag]:
        return sorted((f for f in self.flags.values() if f.area == area), key=lambda f: f.flag_id)

    def by_change(self, cr_id: str) -> DriftFlag | None:
        return next((f for f in self.flags.values() if f.fix and f.fix.change_request_id == cr_id), None)


class PostgresDrift:
    """The drift flags in Postgres. Same answers as MemoryDrift."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)

    def read(self, where: str, args: tuple) -> list[DriftFlag]:
        rows = self.connection.execute(f"SELECT body FROM memory_drift WHERE tenant_id = %s AND {where} ORDER BY flag_id", (self.tenant_id, *args))
        return [DriftFlag.model_validate(row[0]) for row in rows]

    def open_flag(self, kind: str, subject_id: str) -> DriftFlag | None:
        found = self.read("kind = %s AND subject_id = %s AND state <> 'resolved'", (kind, subject_id))
        return found[0] if found else None

    def raise_flag(self, flag: DriftFlag) -> tuple[DriftFlag, bool]:
        # The unique index on open flags decides between two workers: one inserts, the other adds its evidence
        inserted = self.connection.execute(
            """INSERT INTO memory_drift (tenant_id, flag_id, kind, subject_id, area, state, cr_id, body, events) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s)
               ON CONFLICT DO NOTHING""",
            (self.tenant_id, flag.flag_id, flag.kind, flag.subject.id, flag.area, flag.state, Jsonb(flag.model_dump(mode="json")),
             Jsonb([event(flag.state, flag.raised_at, "raised")]))).rowcount
        if inserted:
            return flag, True
        held = self.open_flag(flag.kind, flag.subject.id)
        if held is None:  # the same id was resolved before: a new drift of the same subject keeps the old one as history
            return self.raise_flag(flag.model_copy(update={"flag_id": f"{flag.flag_id}-{flag.raised_at:%Y%m%d%H%M%S}"}))
        updated = with_evidence(held, flag)
        self.connection.execute("UPDATE memory_drift SET body = %s WHERE tenant_id = %s AND flag_id = %s", (Jsonb(updated.model_dump(mode="json")), self.tenant_id, held.flag_id))
        return updated, False

    def move(self, flag: DriftFlag, at: datetime, note: str) -> DriftFlag:
        self.connection.execute(
            "UPDATE memory_drift SET state = %s, cr_id = %s, body = %s, events = events || %s WHERE tenant_id = %s AND flag_id = %s",
            (flag.state, flag.fix.change_request_id if flag.fix else None, Jsonb(flag.model_dump(mode="json")), Jsonb([event(flag.state, at, note)]), self.tenant_id, flag.flag_id))
        return flag

    def get(self, flag_id: str) -> DriftFlag | None:
        found = self.read("flag_id = %s", (flag_id,))
        return found[0] if found else None

    def history(self, flag_id: str) -> list[dict]:
        row = self.connection.execute("SELECT events FROM memory_drift WHERE tenant_id = %s AND flag_id = %s", (self.tenant_id, flag_id)).fetchone()
        return row[0] if row else []

    def in_state(self, state: str) -> list[DriftFlag]:
        return self.read("state = %s", (state,))

    def in_area(self, area: str) -> list[DriftFlag]:
        return self.read("area = %s", (area,))

    def by_change(self, cr_id: str) -> DriftFlag | None:
        found = self.read("cr_id = %s", (cr_id,))
        return found[0] if found else None
