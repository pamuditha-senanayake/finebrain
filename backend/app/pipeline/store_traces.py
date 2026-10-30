# store_traces.py: the living memory's traces (stage 5a), the warm tier: each K16 TraceRecord by id, and one area's
# traces newest first, a page at a time by a keyset cursor, so reading never walks the whole table. Saving the same
# trace twice is a no-op, so a redelivered message or a second worker changes nothing. PostgresTraces and its twin.
# Each task's activity is kept too, so a run's trace can name the policies it was held to (stage 6). Since 5d the nightly tidy moves traces older than 30 days to S3 (older_than, remove). Access decisions arrive on their own topic, sometimes after the run's trace: they are kept by run, and one that comes
# late is attached to the trace already saved. Used by: stages_memory_flow.py, adapters.py, tests/test_memory_stores.py,
# tests/test_memory_flow.py. Uses: contracts_memory.py.
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from app.pipeline.contracts_memory import TraceAccess, TraceRecord

# Config
PAGE_SIZE = 25
SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_traces (
    tenant_id  text        NOT NULL,
    trace_id   text        NOT NULL,
    area       text        NOT NULL,
    started_at timestamptz NOT NULL,
    body       jsonb       NOT NULL,
    PRIMARY KEY (tenant_id, trace_id)
);
CREATE INDEX IF NOT EXISTS memory_traces_area_newest ON memory_traces (tenant_id, area, started_at DESC, trace_id DESC);
CREATE INDEX IF NOT EXISTS memory_traces_oldest ON memory_traces (tenant_id, started_at, trace_id);
CREATE TABLE IF NOT EXISTS memory_access (
    tenant_id   text  NOT NULL,
    decision_id text  NOT NULL,
    run_id      text  NOT NULL,
    body        jsonb NOT NULL,
    PRIMARY KEY (tenant_id, decision_id)
);
CREATE INDEX IF NOT EXISTS memory_access_run ON memory_access (tenant_id, run_id);
CREATE TABLE IF NOT EXISTS memory_tasks (
    tenant_id   text NOT NULL,
    task_id     text NOT NULL,
    activity_id text NOT NULL,
    PRIMARY KEY (tenant_id, task_id)
);
"""


# The cursor is the last row's time and id: the next page starts strictly after it, whatever was added meanwhile.
def cursor_of(trace: TraceRecord) -> str:
    return f"{trace.started_at.isoformat()}|{trace.trace_id}"


def parse_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    at, _, trace_id = cursor.partition("|")
    return datetime.fromisoformat(at), trace_id


def page_of(traces: list[TraceRecord], limit: int) -> tuple[list[TraceRecord], str | None]:
    """The page and the cursor for the next one; None when this page is the last."""
    page = traces[:limit]
    return page, cursor_of(page[-1]) if len(traces) > limit else None


class MemoryTraces:
    """The in-memory twin of PostgresTraces."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.rows: dict[str, TraceRecord] = {}
        self.access: dict[str, dict[str, TraceAccess]] = {}  # run_id to its decisions by id
        self.activities: dict[str, str] = {}  # task_id to its activity, so a run's trace finds the policies it was held to

    def save(self, trace: TraceRecord) -> bool:
        """Keep the trace. False when it was already kept."""
        if trace.trace_id in self.rows:
            return False
        self.rows[trace.trace_id] = trace
        return True

    def get(self, trace_id: str) -> TraceRecord | None:
        return self.rows.get(trace_id)

    def add_access(self, run_id: str, access: TraceAccess) -> bool:
        """Keep an access decision under its run. False when it was already kept."""
        kept = self.access.setdefault(run_id, {})
        if access.decision_id in kept:
            return False
        kept[access.decision_id] = access
        return True

    def access_of(self, run_id: str) -> list[TraceAccess]:
        return list(self.access.get(run_id, {}).values())

    def add_activity(self, task_id: str, activity_id: str) -> None:
        self.activities.setdefault(task_id, activity_id)

    def activity_of(self, task_id: str) -> str | None:
        return self.activities.get(task_id)

    def attach(self, trace_id: str, access: TraceAccess) -> bool:
        """Add a late access decision to a saved trace. False when there is no such trace or it already has it."""
        trace = self.rows.get(trace_id)
        if not trace or any(a.decision_id == access.decision_id for a in trace.access):
            return False
        self.rows[trace_id] = trace.model_copy(update={"access": [*trace.access, access]})
        return True

    def older_than(self, before: datetime, limit: int) -> list[TraceRecord]:
        """The oldest warm traces that started before this moment, oldest first: what the nightly tidy moves to cold."""
        return sorted((t for t in self.rows.values() if t.started_at < before), key=lambda t: (t.started_at, t.trace_id))[:limit]

    def remove(self, trace_id: str) -> bool:
        """Leave the warm tier (the tidy archived it first), with the access decisions kept for its run."""
        trace = self.rows.pop(trace_id, None)
        if trace and trace.run_id:
            self.access.pop(trace.run_id, None)
        return trace is not None

    def scrub(self, trace_id: str, note: str) -> bool:
        """Forgetting (step 10): replace the trace's why lines, which may quote an erased document. False when nothing changed."""
        trace = self.rows.get(trace_id)
        if not trace or trace.why == [note]:
            return False
        self.rows[trace_id] = trace.model_copy(update={"why": [note]})
        return True

    def page(self, area: str, cursor: str | None = None, limit: int = PAGE_SIZE) -> tuple[list[TraceRecord], str | None]:
        after = parse_cursor(cursor)
        newest = sorted((t for t in self.rows.values() if t.area == area), key=lambda t: (t.started_at, t.trace_id), reverse=True)
        if after:
            newest = [t for t in newest if (t.started_at, t.trace_id) < after]
        return page_of(newest, limit)


class PostgresTraces:
    """The traces in Postgres. Same answers as MemoryTraces."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)

    def save(self, trace: TraceRecord) -> bool:
        return bool(self.connection.execute(
            "INSERT INTO memory_traces VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (self.tenant_id, trace.trace_id, trace.area, trace.started_at, Jsonb(trace.model_dump(mode="json")))).rowcount)

    def get(self, trace_id: str) -> TraceRecord | None:
        row = self.connection.execute("SELECT body FROM memory_traces WHERE tenant_id = %s AND trace_id = %s", (self.tenant_id, trace_id)).fetchone()
        return TraceRecord.model_validate(row[0]) if row else None

    def add_access(self, run_id: str, access: TraceAccess) -> bool:
        return bool(self.connection.execute("INSERT INTO memory_access VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                            (self.tenant_id, access.decision_id, run_id, Jsonb(access.model_dump(mode="json")))).rowcount)

    def access_of(self, run_id: str) -> list[TraceAccess]:
        rows = self.connection.execute("SELECT body FROM memory_access WHERE tenant_id = %s AND run_id = %s ORDER BY decision_id", (self.tenant_id, run_id))
        return [TraceAccess.model_validate(row[0]) for row in rows]

    def add_activity(self, task_id: str, activity_id: str) -> None:
        self.connection.execute("INSERT INTO memory_tasks VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (self.tenant_id, task_id, activity_id))

    def activity_of(self, task_id: str) -> str | None:
        row = self.connection.execute("SELECT activity_id FROM memory_tasks WHERE tenant_id = %s AND task_id = %s", (self.tenant_id, task_id)).fetchone()
        return row[0] if row else None

    def attach(self, trace_id: str, access: TraceAccess) -> bool:
        # One statement, so two workers attaching the same decision at once still add it once
        return bool(self.connection.execute(
            """UPDATE memory_traces SET body = jsonb_set(body, '{access}', body->'access' || jsonb_build_array(%s::jsonb))
               WHERE tenant_id = %s AND trace_id = %s AND NOT body->'access' @> jsonb_build_array(jsonb_build_object('decision_id', %s::text))""",
            (Jsonb(access.model_dump(mode="json")), self.tenant_id, trace_id, access.decision_id)).rowcount)

    def older_than(self, before: datetime, limit: int) -> list[TraceRecord]:
        rows = self.connection.execute(
            "SELECT body FROM memory_traces WHERE tenant_id = %s AND started_at < %s ORDER BY started_at, trace_id LIMIT %s", (self.tenant_id, before, limit))
        return [TraceRecord.model_validate(row[0]) for row in rows]

    def remove(self, trace_id: str) -> bool:
        row = self.connection.execute("DELETE FROM memory_traces WHERE tenant_id = %s AND trace_id = %s RETURNING body->>'run_id'", (self.tenant_id, trace_id)).fetchone()
        if row and row[0]:
            self.connection.execute("DELETE FROM memory_access WHERE tenant_id = %s AND run_id = %s", (self.tenant_id, row[0]))
        return row is not None

    def scrub(self, trace_id: str, note: str) -> bool:
        return bool(self.connection.execute(
            "UPDATE memory_traces SET body = jsonb_set(body, '{why}', jsonb_build_array(%s::text)) WHERE tenant_id = %s AND trace_id = %s AND body->'why' <> jsonb_build_array(%s::text)",
            (note, self.tenant_id, trace_id, note)).rowcount)

    def page(self, area: str, cursor: str | None = None, limit: int = PAGE_SIZE) -> tuple[list[TraceRecord], str | None]:
        # One more row than the page tells whether another page follows; the index serves the order and the cursor
        after = parse_cursor(cursor)
        where, args = ("AND (started_at, trace_id) < (%s, %s)", after) if after else ("", ())
        rows = self.connection.execute(
            f"SELECT body FROM memory_traces WHERE tenant_id = %s AND area = %s {where} ORDER BY started_at DESC, trace_id DESC LIMIT %s",
            (self.tenant_id, area, *args, limit + 1))
        return page_of([TraceRecord.model_validate(row[0]) for row in rows], limit)
