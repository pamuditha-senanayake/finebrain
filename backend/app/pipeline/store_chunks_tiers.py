# store_chunks_tiers.py: the chunk columns step 13c adds: each item's value score and its tier (hot, warm or cold), the
# hot-first search, and a cold item's vector leaving (it lives on in the S3 cold archive, stages_cold.py). Kept apart from store_chunks_pg.py so both files stay short; PostgresChunks takes these methods
# from TierColumns. Used by: store_chunks_pg.py. Uses: store_chunks.py (tiers). The memory twin's versions are in store_chunks.py.
import json
from datetime import datetime

from app.pipeline.store_chunks import searched_tiers

# Config
SCHEMA = """
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS value real;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS value_at timestamptz;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tier text NOT NULL DEFAULT 'warm';
CREATE INDEX IF NOT EXISTS chunks_tier ON chunks (tenant_id, tier);
CREATE INDEX IF NOT EXISTS chunks_hot_vector ON chunks USING hnsw (embedding vector_cosine_ops) WHERE tier = 'hot';
ALTER TABLE chunks ALTER COLUMN embedding DROP NOT NULL;
"""
TIER_FILTER = "tier = ANY(%(tiers)s::text[])"


class TierColumns:
    """Methods PostgresChunks shares with no other store, on the value and tier columns. Needs self.connection and self.tenant_id."""

    def value_rows(self) -> list[dict]:
        """What scoring needs about every chunk, without its words or vector."""
        rows = self.connection.execute(
            """SELECT item_id, kind, domain, entity_ids, valid_to, recorded_at, value, tier, embedding IS NOT NULL
               FROM chunks WHERE tenant_id = %s ORDER BY item_id""", (self.tenant_id,))
        return [{"item_id": i, "kind": k, "domain": d, "entity_ids": e, "valid_to": v and v.isoformat(), "recorded_at": r.isoformat(), "value": s,
                 "tier": t, "has_vector": h} for i, k, d, e, v, r, s, t, h in rows]

    def set_values(self, values: dict[str, float], at: datetime) -> None:
        """Write many scores in one statement."""
        self.connection.execute(
            """UPDATE chunks SET value = scored.value, value_at = %s FROM unnest(%s::text[], %s::real[]) AS scored(item_id, value)
               WHERE chunks.tenant_id = %s AND chunks.item_id = scored.item_id""", (at, list(values), list(values.values()), self.tenant_id))

    def set_tiers(self, tiers: dict[str, str]) -> None:
        """Move many items in one statement."""
        self.connection.execute(
            """UPDATE chunks SET tier = moved.tier FROM unnest(%s::text[], %s::text[]) AS moved(item_id, tier)
               WHERE chunks.tenant_id = %s AND chunks.item_id = moved.item_id""", (list(tiers), list(tiers.values()), self.tenant_id))

    def hot_first(self, sql: str, params: dict) -> list[dict]:
        """Run one search on the hot tier (its own small index), then on the other tiers it may read for what is still missing."""
        others = [tier for tier in searched_tiers(params["valid"], params["recorded"]) if tier != "hot"]
        found = [row[0] for row in self.connection.execute(sql, {**params, "tiers": ["hot"]})]
        if len(found) < params["limit"]:
            found += [row[0] for row in self.connection.execute(sql, {**params, "tiers": others, "limit": params["limit"] - len(found)})]
        return found

    def full(self, item_id: str) -> tuple[dict, list[float] | None] | None:
        """The item and its vector (None once it is cold), for the cold archive."""
        found = self.connection.execute("SELECT body, embedding::text FROM chunks WHERE tenant_id = %s AND item_id = %s", (self.tenant_id, item_id)).fetchone()
        return (found[0], json.loads(found[1]) if found[1] else None) if found else None

    def set_vector(self, item_id: str, vector: list[float] | None) -> None:
        """Drop a cold item's vector (its words stay, for history), or give it back when it moves up."""
        self.connection.execute("UPDATE chunks SET embedding = %s::vector WHERE tenant_id = %s AND item_id = %s",
                                (json.dumps(vector) if vector is not None else None, self.tenant_id, item_id))
