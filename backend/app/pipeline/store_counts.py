# store_counts.py: weekly counts for the spike check (step 15). One row per metric, segment and week, and the cases behind
# each count, so a redelivered run is never counted twice and a trend card can link to its runs. PostgresCounts and its twin.
# Used by: adapters.py, stages_learn.py, tests/test_counts.py. Uses: nothing local.
# Sample weeks (a tenant with no history yet) carry a count and no cases; real cases add to whatever the week holds.
from datetime import date

import psycopg

# Config
SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_counts (
    tenant_id text    NOT NULL,
    metric    text    NOT NULL,
    segment   text    NOT NULL,
    week      date    NOT NULL,
    count     integer NOT NULL,
    sample    boolean NOT NULL DEFAULT false,
    PRIMARY KEY (tenant_id, metric, segment, week)
);
CREATE TABLE IF NOT EXISTS signal_count_cases (
    tenant_id text NOT NULL,
    metric    text NOT NULL,
    segment   text NOT NULL,
    week      date NOT NULL,
    case_id   text NOT NULL,
    PRIMARY KEY (tenant_id, metric, segment, week, case_id)
);
"""


class MemoryCounts:
    """The in-memory twin of PostgresCounts."""

    def __init__(self):
        self.rows: dict[tuple[str, str, date], dict] = {}  # (metric, segment, week) to {"count", "sample"}
        self.cases: set[tuple[str, str, date, str]] = set()

    def add(self, metric: str, segment: str, week: date, case_id: str) -> bool:
        """Count one case in its week. False when it was already counted."""
        if (metric, segment, week, case_id) in self.cases:
            return False
        self.cases.add((metric, segment, week, case_id))
        row = self.rows.setdefault((metric, segment, week), {"count": 0, "sample": False})
        row["count"] += 1
        return True

    def add_sample(self, metric: str, segment: str, week: date, count: int) -> None:
        """A sample week, only where the week holds nothing yet: real counts are never overwritten."""
        self.rows.setdefault((metric, segment, week), {"count": count, "sample": True})

    def series(self) -> list[tuple[str, str]]:
        return sorted({(metric, segment) for metric, segment, _ in self.rows})

    def weeks(self, metric: str, segment: str) -> dict[date, int]:
        return {week: row["count"] for (m, s, week), row in sorted(self.rows.items()) if (m, s) == (metric, segment)}

    def cases_of(self, metric: str, segment: str, week: date) -> list[str]:
        return sorted(case for m, s, w, case in self.cases if (m, s, w) == (metric, segment, week))


class PostgresCounts:
    """The counts in Postgres. Same answers as MemoryCounts."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)

    def add(self, metric: str, segment: str, week: date, case_id: str) -> bool:
        # Step 1: remember the case; a redelivery stops here
        key = (self.tenant_id, metric, segment, week)
        added = self.connection.execute("INSERT INTO signal_count_cases VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (*key, case_id)).rowcount
        if not added:
            return False

        # Step 2: one more in its week
        self.connection.execute(
            """INSERT INTO signal_counts (tenant_id, metric, segment, week, count) VALUES (%s, %s, %s, %s, 1)
               ON CONFLICT (tenant_id, metric, segment, week) DO UPDATE SET count = signal_counts.count + 1""", key)
        return True

    def add_sample(self, metric: str, segment: str, week: date, count: int) -> None:
        self.connection.execute("INSERT INTO signal_counts VALUES (%s, %s, %s, %s, %s, true) ON CONFLICT DO NOTHING", (self.tenant_id, metric, segment, week, count))

    def series(self) -> list[tuple[str, str]]:
        rows = self.connection.execute("SELECT DISTINCT metric, segment FROM signal_counts WHERE tenant_id = %s ORDER BY metric, segment", (self.tenant_id,))
        return [(metric, segment) for metric, segment in rows]

    def weeks(self, metric: str, segment: str) -> dict[date, int]:
        rows = self.connection.execute(
            "SELECT week, count FROM signal_counts WHERE tenant_id = %s AND metric = %s AND segment = %s ORDER BY week", (self.tenant_id, metric, segment))
        return {week: count for week, count in rows}

    def cases_of(self, metric: str, segment: str, week: date) -> list[str]:
        rows = self.connection.execute(
            "SELECT case_id FROM signal_count_cases WHERE tenant_id = %s AND metric = %s AND segment = %s AND week = %s ORDER BY case_id",
            (self.tenant_id, metric, segment, week))
        return [row[0] for row in rows]
