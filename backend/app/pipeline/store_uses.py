# store_uses.py: which runs and answers cited which items (step 13c), the "use" in an item's value score. One row per item
# and citer, so a redelivered run never counts twice. Ids and times only, never content. PostgresUses and its twin.
# Used by: adapters.py, stages_value.py, api/ask.py, tests/test_value.py. Uses: nothing local.
from datetime import datetime

import psycopg

# Config
SCHEMA = """
CREATE TABLE IF NOT EXISTS item_uses (
    tenant_id text        NOT NULL,
    item_id   text        NOT NULL,
    used_by   text        NOT NULL,
    used_at   timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, item_id, used_by)
);
"""


class MemoryUses:
    """The in-memory twin of PostgresUses."""

    def __init__(self):
        self.rows: dict[tuple[str, str], datetime] = {}  # (item_id, used_by) to used_at

    def note(self, item_id: str, used_by: str, used_at: datetime) -> bool:
        """One citation. False when this citer was already counted for this item."""
        if (item_id, used_by) in self.rows:
            return False
        self.rows[(item_id, used_by)] = used_at
        return True

    def uses_of(self, item_ids: list[str]) -> dict[str, tuple[int, datetime]]:
        """For each cited item: how many citers, and the latest use."""
        found: dict[str, tuple[int, datetime]] = {}
        wanted = set(item_ids)
        for (item_id, _), used_at in self.rows.items():
            if item_id in wanted:
                count, latest = found.get(item_id, (0, used_at))
                found[item_id] = (count + 1, max(latest, used_at))
        return found


class PostgresUses:
    """Uses in Postgres. Same answers as MemoryUses."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)

    def note(self, item_id: str, used_by: str, used_at: datetime) -> bool:
        return bool(self.connection.execute("INSERT INTO item_uses VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING", (self.tenant_id, item_id, used_by, used_at)).rowcount)

    def uses_of(self, item_ids: list[str]) -> dict[str, tuple[int, datetime]]:
        rows = self.connection.execute(
            "SELECT item_id, count(*), max(used_at) FROM item_uses WHERE tenant_id = %s AND item_id = ANY(%s) GROUP BY item_id", (self.tenant_id, item_ids))
        return {item_id: (count, latest) for item_id, count, latest in rows}
