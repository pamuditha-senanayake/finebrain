# store_chunks_tiers.py: the chunk columns step 13 adds, in Postgres: each item's value and tier (hot, warm or cold), the
# hot-first search, a cold item's vector leaving (the S3 cold archive, stages_cold.py), the summaries built on an item, and
# duplicates of the same words. Kept apart from store_chunks_pg.py so both files stay short; PostgresChunks takes these
# methods from TierColumns. Used by: store_chunks_pg.py. Uses: store_chunks_memory.py (shared settings; the memory versions).
import json
from datetime import datetime

from app.pipeline.store_chunks_memory import SUMMARY_PREFIX, searched_tiers

# Config
SCHEMA = """
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS value real;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS value_at timestamptz;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tier text NOT NULL DEFAULT 'warm';
CREATE INDEX IF NOT EXISTS chunks_tier ON chunks (tenant_id, tier);
CREATE INDEX IF NOT EXISTS chunks_hot_vector ON chunks USING hnsw (embedding vector_cosine_ops) WHERE tier = 'hot';
ALTER TABLE chunks ALTER COLUMN embedding DROP NOT NULL;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS duplicate_of text;
ALTER TABLE chunks DROP COLUMN IF EXISTS fingerprint;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS passage_print text GENERATED ALWAYS AS (md5(trim(lower(regexp_replace(
    CASE WHEN body ? 'title' AND starts_with(body->>'text', (body->>'title') || ': ') THEN substr(body->>'text', length(body->>'title') + 3) ELSE body->>'text' END,
    '[^a-zA-Z0-9]+', ' ', 'g'))))) STORED;
CREATE INDEX IF NOT EXISTS chunks_passage_print ON chunks (tenant_id, passage_print);
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

    def summaries_citing(self, item_ids: list[str]) -> list[str]:
        """Summaries (step 13d) that list any of these items among their sources."""
        rows = self.connection.execute("SELECT item_id FROM chunks WHERE tenant_id = %s AND body->'summary'->'sources' ?| %s::text[] ORDER BY item_id",
                                       (self.tenant_id, item_ids))
        return [row[0] for row in rows]

    def duplicate_groups(self) -> list[list[str]]:
        """Open chunks with the same words, each group best first (highest value, then the earliest). Summaries and facts are left out."""
        rows = self.connection.execute(
            """SELECT array_agg(item_id ORDER BY coalesce(value, 0) DESC, recorded_at, item_id) FROM chunks
               WHERE tenant_id = %s AND kind = 'chunk' AND item_id NOT LIKE %s AND valid_to IS NULL AND duplicate_of IS NULL
               GROUP BY passage_print HAVING count(*) > 1""", (self.tenant_id, SUMMARY_PREFIX.replace("_", "\\_") + "%"))
        return [row[0] for row in rows]

    def mark_duplicates(self, marks: dict[str, str | None]) -> None:
        """Point each item at the one kept for its words, or (None) let it answer again."""
        self.connection.execute(
            """UPDATE chunks SET duplicate_of = marked.kept FROM unnest(%s::text[], %s::text[]) AS marked(item_id, kept)
               WHERE chunks.tenant_id = %s AND chunks.item_id = marked.item_id""", (list(marks), list(marks.values()), self.tenant_id))

    def duplicates_of(self, item_ids: list[str]) -> list[str]:
        rows = self.connection.execute("SELECT item_id FROM chunks WHERE tenant_id = %s AND duplicate_of = ANY(%s) ORDER BY item_id", (self.tenant_id, item_ids))
        return [row[0] for row in rows]
