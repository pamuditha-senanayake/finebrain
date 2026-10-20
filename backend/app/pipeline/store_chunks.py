# store_chunks.py: knowledge chunks for S5: an embedding and a full-text index per chunk, with valid and recorded times,
# and since step 13a a domain and entity tags. MemoryChunks, the twin of PostgresChunks (store_chunks_pg.py), and the
# seed loader. Used by: adapters.py, stages_retrieve.py, store_chunks_pg.py, tests. Uses: observe.py.
# Ranking, access and the token budget are S5's job; this file only finds candidates.
import re
from datetime import datetime

from app.pipeline.observe import log_event

# Config
GENERAL = "general"  # a domain every scope may read


def search_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def true_at(item: dict, valid, recorded) -> bool:
    """Bitemporal check: valid at `valid`, and already known at `recorded`."""
    start, end, known = (datetime.fromisoformat(item[key]) if item.get(key) else None for key in ("valid_from", "valid_to", "recorded_at"))
    return (start is None or start <= valid) and (end is None or end > valid) and known <= recorded


def in_scope(item: dict, scope: dict | None) -> bool:
    """Inside the scope's domains (or general, or untagged), and about its entities (or about no entity at all)."""
    if not scope:
        return True
    domain, tags = item.get("domain"), item.get("entity_ids") or []
    domain_ok = not scope["domains"] or domain in (None, GENERAL, *scope["domains"])
    return domain_ok and (not scope["entity_ids"] or not tags or bool(set(tags) & set(scope["entity_ids"])))


class MemoryChunks:
    """The in-memory twin of PostgresChunks."""

    def __init__(self):
        self.items: dict[str, tuple[dict, list[float]]] = {}

    def add(self, item: dict, embedding: list[float]) -> None:
        self.items.setdefault(item["item_id"], (item, embedding))

    def replace(self, item: dict, embedding: list[float]) -> None:
        """A released new version of a knowledge item takes the place of the old one."""
        self.items[item["item_id"]] = (item, embedding)

    def known(self, item_ids: list[str]) -> set[str]:
        return {item_id for item_id in item_ids if item_id in self.items}

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

    def retag(self, item_id: str, domain: str, entity_ids: list[str]) -> None:
        if item_id in self.items:
            item, vector = self.items[item_id]
            self.items[item_id] = ({**item, "domain": domain, "entity_ids": entity_ids}, vector)

    def untagged(self) -> list[dict]:
        return sorted((item for item, _ in self.items.values() if item.get("domain") is None), key=lambda item: item["item_id"])

    def value_rows(self) -> list[dict]:
        """What scoring needs about every chunk (step 13c)."""
        return sorted(({**item, "value": item.get("value")} for item, _ in self.items.values()), key=lambda item: item["item_id"])

    def set_values(self, values: dict[str, float], at: datetime) -> None:
        for item_id, value in values.items():
            if item_id in self.items:
                item, vector = self.items[item_id]
                self.items[item_id] = ({**item, "value": value}, vector)

    def live(self, kinds: list[str], valid, recorded, scope: dict | None) -> list[tuple[dict, list[float]]]:
        return [(item, vector) for item, vector in self.items.values() if item["kind"] in kinds and true_at(item, valid, recorded) and in_scope(item, scope)]

    def by_vector(self, embedding: list[float], kinds: list[str], valid, recorded, limit: int, scope: dict | None = None) -> list[dict]:
        """Nearest by cosine similarity (the vectors are already unit length), inside the scope."""
        live = self.live(kinds, valid, recorded, scope)
        ranked = sorted(live, key=lambda pair: -sum(a * b for a, b in zip(embedding, pair[1])))
        return [item for item, _ in ranked[:limit]]

    def by_text(self, query: str, kinds: list[str], valid, recorded, limit: int, scope: dict | None = None) -> list[dict]:
        """Items sharing any query word, most shared words first, inside the scope."""
        asked = set(search_words(query))
        live = [item for item, _ in self.live(kinds, valid, recorded, scope)]
        scored = [(len(asked & set(search_words(item["text"]))), item) for item in live]
        return [item for hits, item in sorted(scored, key=lambda pair: -pair[0]) if hits][:limit]


def load_chunks(chunks, graph, embed, tag=lambda item: item) -> None:
    """Embed the knowledge nodes the index does not hold yet, tagged by `tag`. Safe to run twice, and on a restart it embeds nothing.
    A refusing embedding service never stops the API from starting: what is already indexed stays searchable."""
    nodes = graph.latest("knowledge")
    known = chunks.known([node["_ref"]["id"] for node in nodes])
    items = [tag({key: value for key, value in node.items() if key != "_ref"}) for node in nodes if node["_ref"]["id"] not in known]
    if not items:
        return
    try:
        vectors = embed([item["text"] for item in items], "document")
    except Exception as error:  # a rate limit at startup: the missing items wait for the next start
        log_event("S5", "seed_not_embedded", items=len(items), error=type(error).__name__)
        return
    for item, vector in zip(items, vectors):
        chunks.add(item, vector)
