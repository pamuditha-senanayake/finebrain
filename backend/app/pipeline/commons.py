# commons.py: the shared commons (step 13e). Knowledge that is the same for many tenants (laws, rates, deadlines) is stored
# once per collection, read only, under its own id in the chunks store ("commons:<collection>"). A tenant links to a
# collection by listing it in its seed ("commons"); S5 then searches it beside the tenant's own items, without copying it.
# Used by: adapters.py, scripts/commons_admin.py, tests/test_commons.py. Uses: samples/commons/<collection>.json.
import json
from pathlib import Path

# Config
COMMONS_DIR = Path(__file__).resolve().parents[2] / "samples" / "commons"
PREFIX = "commons:"


def store_id(collection: str) -> str:
    """The id a collection is stored under, as if it were a tenant of its own."""
    return f"{PREFIX}{collection}"


def linked(seed: dict) -> list[str]:
    """The collections a tenant reads."""
    return list(seed.get("commons", []))


def items_of(collection: str) -> list[dict]:
    """A collection's items as chunks: public, about no entity, known since they hold."""
    data = json.loads((COMMONS_DIR / f"{collection}.json").read_text())
    return [{"item_id": f"commons_{collection}_{entry['id']}", "kind": "chunk", "text": entry["text"], "domain": entry["domain"], "entity_ids": [],
             "source": {"document_id": store_id(collection), "uri": entry["uri"]}, "valid_from": f"{entry['valid_from']}T00:00:00+00:00", "valid_to": None,
             "recorded_at": f"{entry['valid_from']}T00:00:00+00:00", "sensitivity": "public", "verified_by": "commons", "version_ref": None, "score": 0.0,
             "commons": collection} for entry in data["items"]]


def load(store, embed, collection: str) -> int:
    """Write a collection into its store, replacing what changed. Only the commons admin does this; tenants only read."""
    items = items_of(collection)
    for item, vector in zip(items, embed([item["text"] for item in items], "document")):
        store.replace(item, vector)
    return len(items)
