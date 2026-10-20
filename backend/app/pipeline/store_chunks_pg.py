# store_chunks_pg.py: PostgresChunks, knowledge chunks in Postgres: pgvector for meaning, a tsvector for exact words, and
# since step 13a the domain and entity tags as columns, so search can narrow before it ranks.
# Used by: adapters.py, scripts/backfill_tags.py, tests. Uses: store_chunks.py (search_words), store_chunks_tiers.py (value and tier columns). The memory twin is in store_chunks.py.
import json
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from app.pipeline import store_chunks_tiers
from app.pipeline.store_chunks_tiers import TIER_FILTER
from app.pipeline.store_chunks import GENERAL, search_words

# Config
EMBEDDING_SIZE = 1024
SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
    tenant_id   text        NOT NULL,
    item_id     text        NOT NULL,
    kind        text        NOT NULL,
    body        jsonb       NOT NULL,
    valid_from  timestamptz,
    valid_to    timestamptz,
    recorded_at timestamptz NOT NULL,
    embedding   vector({EMBEDDING_SIZE}) NOT NULL,
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', body->>'text')) STORED,
    PRIMARY KEY (tenant_id, item_id)
);
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin (tsv);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS domain text;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS entity_ids text[] NOT NULL DEFAULT '{{}}';
CREATE INDEX IF NOT EXISTS chunks_domain ON chunks (tenant_id, domain);
CREATE INDEX IF NOT EXISTS chunks_entities ON chunks USING gin (entity_ids);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS scope_keys text[] GENERATED ALWAYS AS
    (CASE WHEN cardinality(entity_ids) = 0 THEN ARRAY[tenant_id || ':general'] ELSE entity_ids END) STORED;
CREATE INDEX IF NOT EXISTS chunks_scope_keys ON chunks USING gin (scope_keys);
"""
TIME_FILTER = """kind = ANY(%(kinds)s)
    AND (valid_from IS NULL OR valid_from <= %(valid)s) AND (valid_to IS NULL OR valid_to > %(valid)s)
    AND recorded_at <= %(recorded)s"""
# Inside the scope's domains (or general, or untagged), and about its entities (or about no entity at all). The entity part is
# one test on scope_keys (a chunk's entities, or the tenant's general key), so its GIN index finds the slice without a full scan
DOMAIN_FILTER = "(domain IS NULL OR domain = %(general)s OR domain = ANY(%(domains)s::text[]))"
ENTITY_FILTER = "scope_keys && %(keys)s::text[]"
UPSERT = """INSERT INTO chunks (tenant_id, item_id, kind, body, valid_from, valid_to, recorded_at, embedding, domain, entity_ids)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)"""


def scope_filter(scope: dict | None) -> str:
    """Only the filters that apply, never "no entities OR ...": a prepared statement's generic plan cannot drop that branch,
    and then it scans every chunk instead of using the index."""
    parts = ["TRUE"]
    if scope and scope["domains"]:
        parts.append(DOMAIN_FILTER)
    if scope and scope["entity_ids"]:
        parts.append(ENTITY_FILTER)
    return " AND ".join(parts)


class PostgresChunks(store_chunks_tiers.TierColumns):
    """Chunks in Postgres. A domain of NULL means the chunk was stored before step 13a and still waits for the back-fill."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)
        connection.execute(store_chunks_tiers.SCHEMA)

    def row(self, item: dict, embedding: list[float]) -> tuple:
        return (self.tenant_id, item["item_id"], item["kind"], Jsonb(item), item.get("valid_from"), item.get("valid_to"), item["recorded_at"],
                json.dumps(embedding), item.get("domain"), item.get("entity_ids", []))

    def add(self, item: dict, embedding: list[float]) -> None:
        self.connection.execute(f"{UPSERT} ON CONFLICT DO NOTHING", self.row(item, embedding))

    def replace(self, item: dict, embedding: list[float]) -> None:
        """A released new version of a knowledge item takes the place of the old one."""
        self.connection.execute(
            f"""{UPSERT} ON CONFLICT (tenant_id, item_id) DO UPDATE SET kind = EXCLUDED.kind, body = EXCLUDED.body, valid_from = EXCLUDED.valid_from,
                 valid_to = EXCLUDED.valid_to, recorded_at = EXCLUDED.recorded_at, embedding = EXCLUDED.embedding,
                 domain = EXCLUDED.domain, entity_ids = EXCLUDED.entity_ids""", self.row(item, embedding))

    def retag(self, item_id: str, domain: str, entity_ids: list[str]) -> None:
        """Set the tags of a stored chunk, in its columns and its body. The embedding stays, so nothing is paid again."""
        self.connection.execute(
            """UPDATE chunks SET domain = %(domain)s, entity_ids = %(ids)s,
                 body = body || jsonb_build_object('domain', %(domain)s::text, 'entity_ids', to_jsonb(%(ids)s::text[]))
               WHERE tenant_id = %(tenant)s AND item_id = %(item)s""", {"domain": domain, "ids": entity_ids, "tenant": self.tenant_id, "item": item_id})

    def untagged(self) -> list[dict]:
        """Chunks stored before step 13a, for the back-fill."""
        rows = self.connection.execute("SELECT body FROM chunks WHERE tenant_id = %s AND domain IS NULL ORDER BY item_id", (self.tenant_id,))
        return [row[0] for row in rows]

    def known(self, item_ids: list[str]) -> set[str]:
        """Which of these items the index already holds, so a restart does not embed them again."""
        rows = self.connection.execute("SELECT item_id FROM chunks WHERE tenant_id = %s AND item_id = ANY(%s)", (self.tenant_id, item_ids))
        return {row[0] for row in rows}

    def of_document(self, document_id: str) -> list[dict]:
        """Every chunk filed from one document, live or retired, ordered by id."""
        rows = self.connection.execute(
            "SELECT body FROM chunks WHERE tenant_id = %s AND body->'source'->>'document_id' = %s ORDER BY item_id", (self.tenant_id, document_id))
        return [row[0] for row in rows]

    def retire(self, item_id: str, when: datetime) -> None:
        """No longer true from `when`: an as-of search before then still finds it."""
        self.connection.execute(
            "UPDATE chunks SET valid_to = %s, body = jsonb_set(body, '{valid_to}', to_jsonb(%s::text)) WHERE tenant_id = %s AND item_id = %s",
            (when, when.isoformat(), self.tenant_id, item_id))

    def delete(self, item_id: str) -> None:
        self.connection.execute("DELETE FROM chunks WHERE tenant_id = %s AND item_id = %s", (self.tenant_id, item_id))

    def filters(self, kinds: list[str], valid, recorded, limit: int, scope: dict | None) -> dict:
        """The parameters every search shares: tenant, kinds, as-of times, limit and the scope."""
        scope = scope or {"domains": [], "entity_ids": []}
        return {"tenant": self.tenant_id, "kinds": kinds, "valid": valid, "recorded": recorded, "limit": limit, "domains": scope["domains"],
                "ids": scope["entity_ids"], "keys": [*scope["entity_ids"], f"{self.tenant_id}:{GENERAL}"], "general": GENERAL}

    def by_vector(self, embedding: list[float], kinds: list[str], valid, recorded, limit: int, scope: dict | None = None) -> list[dict]:
        """Nearest by cosine distance, inside the scope, hot first."""
        return self.hot_first(
            f"""SELECT body FROM chunks WHERE tenant_id = %(tenant)s AND {TIME_FILTER} AND {TIER_FILTER} AND {scope_filter(scope)}
                ORDER BY embedding <=> %(vector)s::vector LIMIT %(limit)s""",
            {**self.filters(kinds, valid, recorded, limit, scope), "vector": json.dumps(embedding)},
        )

    def by_text(self, query: str, kinds: list[str], valid, recorded, limit: int, scope: dict | None = None) -> list[dict]:
        """Full-text match on any query word, best rank first, inside the scope, hot first."""
        terms = " | ".join(search_words(query)) or "nothing"
        return self.hot_first(
            f"""SELECT body FROM chunks, to_tsquery('english', %(terms)s) AS asked WHERE tenant_id = %(tenant)s AND {TIME_FILTER} AND {TIER_FILTER}
                AND {scope_filter(scope)} AND tsv @@ asked ORDER BY ts_rank(tsv, asked) DESC LIMIT %(limit)s""",
            {**self.filters(kinds, valid, recorded, limit, scope), "terms": terms},
        )
