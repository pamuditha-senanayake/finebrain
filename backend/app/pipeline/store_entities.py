# store_entities.py: the entity registry (step 13a). One row per real thing (a customer, a payment, a document), the
# sources that mention it, and typed links between things. PostgresEntities and its in-memory twin.
# Used by: adapters.py, entity_match.py, api/forget_layers_data.py, tests/test_entities.py. Uses: nothing local.
# An entity lives while something mentions it: dropping its last source removes it, so forgetting needs no extra rule.
from datetime import datetime

import psycopg

# Config
SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    tenant_id  text        NOT NULL,
    entity_id  text        NOT NULL,
    type       text        NOT NULL,
    key        text        NOT NULL,
    first_seen timestamptz NOT NULL,
    last_seen  timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, entity_id)
);
CREATE TABLE IF NOT EXISTS entity_mentions (
    tenant_id text        NOT NULL,
    entity_id text        NOT NULL,
    source_id text        NOT NULL,
    seen_at   timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, entity_id, source_id)
);
CREATE INDEX IF NOT EXISTS entity_mentions_source ON entity_mentions (tenant_id, source_id);
CREATE TABLE IF NOT EXISTS entity_links (
    tenant_id text        NOT NULL,
    from_id   text        NOT NULL,
    rel       text        NOT NULL,
    to_id     text        NOT NULL,
    source_id text        NOT NULL,
    seen_at   timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, from_id, rel, to_id, source_id)
);
CREATE INDEX IF NOT EXISTS entity_links_to ON entity_links (tenant_id, to_id);
"""


class MemoryEntities:
    """The in-memory twin of PostgresEntities."""

    def __init__(self):
        self.entities: dict[str, dict] = {}
        self.mentions: set[tuple[str, str]] = set()  # (entity_id, source_id)
        self.links: set[tuple[str, str, str, str]] = set()  # (from_id, rel, to_id, source_id)

    def note(self, entity_id: str, entity_type: str, key: str, source_id: str, seen_at: datetime) -> None:
        """Add the entity if it is new, move its last_seen forward, and remember who mentioned it."""
        seen = seen_at.isoformat()
        known = self.entities.setdefault(entity_id, {"entity_id": entity_id, "type": entity_type, "key": key, "first_seen": seen, "last_seen": seen})
        known["last_seen"] = max(known["last_seen"], seen)
        self.mentions.add((entity_id, source_id))

    def link(self, from_id: str, rel: str, to_id: str, source_id: str, seen_at: datetime) -> None:
        self.links.add((from_id, rel, to_id, source_id))

    def get(self, entity_id: str) -> dict | None:
        return self.entities.get(entity_id)

    def all(self) -> list[dict]:
        return sorted(self.entities.values(), key=lambda entity: entity["entity_id"])

    def sources_of(self, entity_id: str) -> list[str]:
        return sorted(source for known, source in self.mentions if known == entity_id)

    def links_of(self, entity_id: str) -> list[dict]:
        """Typed links touching this entity, in either direction."""
        found = [link for link in self.links if entity_id in (link[0], link[2])]
        return [{"from_id": f, "rel": r, "to_id": t, "source_id": s} for f, r, t, s in sorted(found)]

    def of_source(self, source_id: str) -> list[str]:
        """Entities this source mentions."""
        return sorted(entity_id for entity_id, source in self.mentions if source == source_id)

    def drop_source(self, source_id: str) -> int:
        """Forget what one source said: its mentions, its links, and entities nothing else mentions. Returns rows removed."""
        mentioned = self.of_source(source_id)
        links = {link for link in self.links if link[3] == source_id}
        self.links -= links
        self.mentions -= {(entity_id, source_id) for entity_id in mentioned}
        orphans = [entity_id for entity_id in mentioned if not self.sources_of(entity_id)]
        for entity_id in orphans:
            self.entities.pop(entity_id, None)
        return len(mentioned) + len(links) + len(orphans)


class PostgresEntities:
    """The registry in Postgres. Same answers as MemoryEntities."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)

    def note(self, entity_id: str, entity_type: str, key: str, source_id: str, seen_at: datetime) -> None:
        self.connection.execute(
            """INSERT INTO entities (tenant_id, entity_id, type, key, first_seen, last_seen) VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (tenant_id, entity_id) DO UPDATE SET last_seen = greatest(entities.last_seen, EXCLUDED.last_seen)""",
            (self.tenant_id, entity_id, entity_type, key, seen_at, seen_at))
        self.connection.execute("INSERT INTO entity_mentions VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING", (self.tenant_id, entity_id, source_id, seen_at))

    def link(self, from_id: str, rel: str, to_id: str, source_id: str, seen_at: datetime) -> None:
        self.connection.execute("INSERT INTO entity_links VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (self.tenant_id, from_id, rel, to_id, source_id, seen_at))

    def get(self, entity_id: str) -> dict | None:
        found = self.select("WHERE tenant_id = %s AND entity_id = %s", (self.tenant_id, entity_id))
        return found[0] if found else None

    def all(self) -> list[dict]:
        return self.select("WHERE tenant_id = %s ORDER BY entity_id", (self.tenant_id,))

    def select(self, where: str, params: tuple) -> list[dict]:
        rows = self.connection.execute(f"SELECT entity_id, type, key, first_seen, last_seen FROM entities {where}", params)
        return [{"entity_id": i, "type": t, "key": k, "first_seen": f.isoformat(), "last_seen": s.isoformat()} for i, t, k, f, s in rows]

    def sources_of(self, entity_id: str) -> list[str]:
        rows = self.connection.execute("SELECT source_id FROM entity_mentions WHERE tenant_id = %s AND entity_id = %s ORDER BY source_id", (self.tenant_id, entity_id))
        return [row[0] for row in rows]

    def links_of(self, entity_id: str) -> list[dict]:
        rows = self.connection.execute(
            """SELECT from_id, rel, to_id, source_id FROM entity_links WHERE tenant_id = %(t)s AND (from_id = %(e)s OR to_id = %(e)s)
               ORDER BY from_id, rel, to_id, source_id""", {"t": self.tenant_id, "e": entity_id})
        return [{"from_id": f, "rel": r, "to_id": t, "source_id": s} for f, r, t, s in rows]

    def of_source(self, source_id: str) -> list[str]:
        rows = self.connection.execute("SELECT entity_id FROM entity_mentions WHERE tenant_id = %s AND source_id = %s ORDER BY entity_id", (self.tenant_id, source_id))
        return [row[0] for row in rows]

    def drop_source(self, source_id: str) -> int:
        # Step 1: the source's links and mentions go
        links = self.connection.execute("DELETE FROM entity_links WHERE tenant_id = %s AND source_id = %s", (self.tenant_id, source_id)).rowcount
        mentioned = [row[0] for row in self.connection.execute(
            "DELETE FROM entity_mentions WHERE tenant_id = %s AND source_id = %s RETURNING entity_id", (self.tenant_id, source_id))]

        # Step 2: an entity nothing else mentions goes too
        orphans = self.connection.execute(
            """DELETE FROM entities e WHERE e.tenant_id = %s AND e.entity_id = ANY(%s)
               AND NOT EXISTS (SELECT 1 FROM entity_mentions m WHERE m.tenant_id = e.tenant_id AND m.entity_id = e.entity_id)""",
            (self.tenant_id, mentioned)).rowcount
        return len(mentioned) + links + orphans
