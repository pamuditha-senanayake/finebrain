# store_chunks.py: knowledge chunks for S5: an embedding (pgvector) and a full-text index per chunk, with valid
# and recorded times. PostgresChunks and its in-memory twin. Used by: adapters.py, stages_retrieve.py, tests.
# Uses: nothing local. Ranking, access and the token budget are S5's job; this file only finds candidates.
import json
import re
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

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
"""
TIME_FILTER = """kind = ANY(%(kinds)s)
    AND (valid_from IS NULL OR valid_from <= %(valid)s) AND (valid_to IS NULL OR valid_to > %(valid)s)
    AND recorded_at <= %(recorded)s"""


def search_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def true_at(item: dict, valid, recorded) -> bool:
    """Bitemporal check: valid at `valid`, and already known at `recorded`."""
    start, end, known = (datetime.fromisoformat(item[key]) if item.get(key) else None for key in ("valid_from", "valid_to", "recorded_at"))
    return (start is None or start <= valid) and (end is None or end > valid) and known <= recorded


class MemoryChunks:
    """The in-memory twin of PostgresChunks."""

    def __init__(self):
        self.items: dict[str, tuple[dict, list[float]]] = {}

    def add(self, item: dict, embedding: list[float]) -> None:
        self.items.setdefault(item["item_id"], (item, embedding))

    def replace(self, item: dict, embedding: list[float]) -> None:
        """A released new version of a knowledge item takes the place of the old one."""
        self.items[item["item_id"]] = (item, embedding)

    def of_document(self, document_id: str) -> list[dict]:
        """Every chunk filed from one document, live or retired, ordered by id."""
        return sorted((item for item, _ in self.items.values() if item.get("source", {}).get("document_id") == document_id), key=lambda item: item["item_id"])

    def retire(self, item_id: str, when: datetime) -> None:
        """No longer true from `when`: an as-of search before then still finds it."""
        if item_id in self.items:
            item, vector = self.items[item_id]
            self.items[item_id] = ({**item, "valid_to": when.isoformat()}, vector)

    def delete(self, item_id: str) -> None:
        self.items.pop(item_id, None)

    def by_vector(self, embedding: list[float], kinds: list[str], valid, recorded, limit: int) -> list[dict]:
        """Nearest by cosine similarity (the vectors are already unit length)."""
        live = [(item, vector) for item, vector in self.items.values() if item["kind"] in kinds and true_at(item, valid, recorded)]
        ranked = sorted(live, key=lambda pair: -sum(a * b for a, b in zip(embedding, pair[1])))
        return [item for item, _ in ranked[:limit]]

    def by_text(self, query: str, kinds: list[str], valid, recorded, limit: int) -> list[dict]:
        """Items sharing any query word, most shared words first."""
        asked = set(search_words(query))
        live = [item for item, _ in self.items.values() if item["kind"] in kinds and true_at(item, valid, recorded)]
        scored = [(len(asked & set(search_words(item["text"]))), item) for item in live]
        return [item for hits, item in sorted(scored, key=lambda pair: -pair[0]) if hits][:limit]


class PostgresChunks:
    """Chunks in Postgres: pgvector for meaning, a tsvector index for exact words."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)

    def add(self, item: dict, embedding: list[float]) -> None:
        self.connection.execute(
            """INSERT INTO chunks (tenant_id, item_id, kind, body, valid_from, valid_to, recorded_at, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING""",
            (self.tenant_id, item["item_id"], item["kind"], Jsonb(item), item.get("valid_from"), item.get("valid_to"), item["recorded_at"], json.dumps(embedding)),
        )

    def replace(self, item: dict, embedding: list[float]) -> None:
        """A released new version of a knowledge item takes the place of the old one."""
        self.connection.execute(
            """INSERT INTO chunks (tenant_id, item_id, kind, body, valid_from, valid_to, recorded_at, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
               ON CONFLICT (tenant_id, item_id) DO UPDATE SET kind = EXCLUDED.kind, body = EXCLUDED.body, valid_from = EXCLUDED.valid_from,
                 valid_to = EXCLUDED.valid_to, recorded_at = EXCLUDED.recorded_at, embedding = EXCLUDED.embedding""",
            (self.tenant_id, item["item_id"], item["kind"], Jsonb(item), item.get("valid_from"), item.get("valid_to"), item["recorded_at"], json.dumps(embedding)),
        )

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

    def by_vector(self, embedding: list[float], kinds: list[str], valid, recorded, limit: int) -> list[dict]:
        """Nearest by cosine distance."""
        rows = self.connection.execute(
            f"SELECT body FROM chunks WHERE tenant_id = %(tenant)s AND {TIME_FILTER} ORDER BY embedding <=> %(vector)s::vector LIMIT %(limit)s",
            {"tenant": self.tenant_id, "kinds": kinds, "valid": valid, "recorded": recorded, "vector": json.dumps(embedding), "limit": limit},
        )
        return [row[0] for row in rows]

    def by_text(self, query: str, kinds: list[str], valid, recorded, limit: int) -> list[dict]:
        """Full-text match on any query word, best rank first."""
        terms = " | ".join(search_words(query)) or "nothing"
        rows = self.connection.execute(
            f"""SELECT body FROM chunks, to_tsquery('english', %(terms)s) AS asked
                WHERE tenant_id = %(tenant)s AND {TIME_FILTER} AND tsv @@ asked ORDER BY ts_rank(tsv, asked) DESC LIMIT %(limit)s""",
            {"tenant": self.tenant_id, "kinds": kinds, "valid": valid, "recorded": recorded, "terms": terms, "limit": limit},
        )
        return [row[0] for row in rows]


def load_chunks(chunks, graph, embed) -> None:
    """Embed every knowledge node in the graph and store it as a chunk. Safe to run twice."""
    items = [{key: value for key, value in node.items() if key != "_ref"} for node in graph.latest("knowledge")]
    if not items:
        return
    for item, vector in zip(items, embed([item["text"] for item in items], "document")):
        chunks.add(item, vector)
