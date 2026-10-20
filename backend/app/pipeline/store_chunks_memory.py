# store_chunks_memory.py: what step 13 adds to the chunk stores, in memory, plus the settings both stores share. Each item's
# value and tier (13c), its vector leaving when it goes cold, the summaries built on it (13d), and duplicates of the same
# words (13d): MemoryChunks (store_chunks.py) takes these methods from MemoryTierColumns; Postgres has the same in
# store_chunks_tiers.py. Used by: store_chunks.py, store_chunks_tiers.py, tests. Uses: nothing local.
import hashlib
import re
from datetime import datetime, timedelta

# Config
WARM = "warm"  # where a new item starts; the nightly mover places it (stages_tiers.py)
NOW_TIERS, ALL_TIERS = ("hot", "warm"), ("hot", "warm", "cold")
HISTORY_GAP = timedelta(days=1)  # an "as of" further back than this is a question about history, which may read cold
SUMMARY_PREFIX = "sum_"  # summaries are never merged as duplicates: two entities may share a sentence


def searched_tiers(valid, recorded) -> tuple[str, ...]:
    """What is true now lives in hot and warm; only a question about the past also reads cold."""
    return ALL_TIERS if valid < recorded - HISTORY_GAP else NOW_TIERS


def passage_of(item: dict) -> str:
    """A document chunk's words without its document's title, so the same passage in two documents matches."""
    title, text = item.get("title"), item["text"]
    return text[len(title) + 2:] if title and text.startswith(f"{title}: ") else text


def fingerprint(text: str) -> str:
    """The same words, whatever the case, spacing or punctuation. Postgres computes the same in a column (passage_print)."""
    return hashlib.md5(re.sub(r"[^a-zA-Z0-9]+", " ", text).lower().strip().encode()).hexdigest()


class MemoryTierColumns:
    """Methods MemoryChunks shares with no other store. Needs self.items: item_id to (item, vector)."""

    def value_rows(self) -> list[dict]:
        """What scoring needs about every chunk."""
        return sorted(({**item, "value": item.get("value"), "tier": item.get("tier", WARM), "has_vector": vector is not None} for item, vector in self.items.values()),
                      key=lambda item: item["item_id"])

    def set_values(self, values: dict[str, float], at: datetime) -> None:
        self.set_field("value", values)

    def set_tiers(self, tiers: dict[str, str]) -> None:
        self.set_field("tier", tiers)

    def full(self, item_id: str) -> tuple[dict, list[float] | None] | None:
        """The item and its vector (None once it is cold), for the cold archive."""
        return self.items.get(item_id)

    def set_vector(self, item_id: str, vector: list[float] | None) -> None:
        """Drop a cold item's vector, or give it back when it moves up."""
        if item_id in self.items:
            self.items[item_id] = (self.items[item_id][0], vector)

    def summaries_citing(self, item_ids: list[str]) -> list[str]:
        """Summaries that list any of these items among their sources."""
        wanted = set(item_ids)
        return sorted(item_id for item_id, (item, _) in self.items.items() if wanted & set((item.get("summary") or {}).get("sources", [])))

    def duplicate_groups(self) -> list[list[str]]:
        """Open chunks with the same words, each group best first (highest value, then the earliest). Summaries and facts are left out."""
        groups: dict[str, list[dict]] = {}
        for item, _ in self.items.values():
            if item["kind"] == "chunk" and not item["item_id"].startswith(SUMMARY_PREFIX) and not item.get("valid_to") and not item.get("duplicate_of"):
                groups.setdefault(fingerprint(passage_of(item)), []).append(item)
        ranked = [sorted(group, key=lambda i: (-(i.get("value") or 0), i["recorded_at"], i["item_id"])) for group in groups.values() if len(group) > 1]
        return [[item["item_id"] for item in group] for group in ranked]

    def mark_duplicates(self, marks: dict[str, str | None]) -> None:
        """Point each item at the one kept for its words, or (None) let it answer again."""
        self.set_field("duplicate_of", marks)

    def duplicates_of(self, item_ids: list[str]) -> list[str]:
        wanted = set(item_ids)
        return sorted(item_id for item_id, (item, _) in self.items.items() if item.get("duplicate_of") in wanted)

    def set_field(self, field: str, by_item: dict) -> None:
        for item_id, value in by_item.items():
            if item_id in self.items:
                item, vector = self.items[item_id]
                self.items[item_id] = ({**item, field: value}, vector)
