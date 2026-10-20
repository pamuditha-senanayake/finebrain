# store_chunks_tiers.py: the chunk columns step 13c adds: each item's value score (and, from slice 2, its tier). Kept apart
# from store_chunks_pg.py so both files stay short; PostgresChunks takes these methods from TierColumns.
# Used by: store_chunks_pg.py. Uses: nothing local. The memory twin's versions are in store_chunks.py.
from datetime import datetime

# Config
SCHEMA = """
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS value real;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS value_at timestamptz;
"""


class TierColumns:
    """Methods PostgresChunks shares with no other store, on the value (and tier) columns. Needs self.connection and self.tenant_id."""

    def value_rows(self) -> list[dict]:
        """What scoring needs about every chunk, without its words or vector."""
        rows = self.connection.execute(
            "SELECT item_id, kind, domain, entity_ids, valid_to, recorded_at, value FROM chunks WHERE tenant_id = %s ORDER BY item_id", (self.tenant_id,))
        return [{"item_id": i, "kind": k, "domain": d, "entity_ids": e, "valid_to": v and v.isoformat(), "recorded_at": r.isoformat(), "value": s}
                for i, k, d, e, v, r, s in rows]

    def set_values(self, values: dict[str, float], at: datetime) -> None:
        """Write many scores in one statement."""
        self.connection.execute(
            """UPDATE chunks SET value = scored.value, value_at = %s FROM unnest(%s::text[], %s::real[]) AS scored(item_id, value)
               WHERE chunks.tenant_id = %s AND chunks.item_id = scored.item_id""", (at, list(values), list(values.values()), self.tenant_id))
