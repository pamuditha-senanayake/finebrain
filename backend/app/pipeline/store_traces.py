# store_traces.py: the living memory's traces (stage 5a), the warm tier: each K16 TraceRecord by id, and one area's
# traces newest first, a page at a time by a keyset cursor, so reading never walks the whole table. Saving the same
# trace twice is a no-op, so a redelivered message or a second worker changes nothing. PostgresTraces and its twin.
# Used by: tests/test_memory_stores.py; stage 5b wires it into the pipeline. Uses: contracts_memory.py.
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from app.pipeline.contracts_memory import TraceRecord

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

    def save(self, trace: TraceRecord) -> bool:
        """Keep the trace. False when it was already kept."""
        if trace.trace_id in self.rows:
            return False
        self.rows[trace.trace_id] = trace
        return True

    def get(self, trace_id: str) -> TraceRecord | None:
        return self.rows.get(trace_id)

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

    def page(self, area: str, cursor: str | None = None, limit: int = PAGE_SIZE) -> tuple[list[TraceRecord], str | None]:
        # One more row than the page tells whether another page follows; the index serves the order and the cursor
        after = parse_cursor(cursor)
        where, args = ("AND (started_at, trace_id) < (%s, %s)", after) if after else ("", ())
        rows = self.connection.execute(
            f"SELECT body FROM memory_traces WHERE tenant_id = %s AND area = %s {where} ORDER BY started_at DESC, trace_id DESC LIMIT %s",
            (self.tenant_id, area, *args, limit + 1))
        return page_of([TraceRecord.model_validate(row[0]) for row in rows], limit)
