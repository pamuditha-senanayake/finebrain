# stages_cold.py: the cold and raw tiers (step 13c). An item moving to cold is archived to S3, compressed, with its vector;
# Postgres then drops the vector and keeps its words, so a question about the past still finds it by word search. Moving
# back up restores the vector from the archive. Raw originals (S1's bodies) are deleted once their 90 days end, leaving a
# tombstone and an audit entry. Used by: stages_tiers.py, api/memory_routes.py, api/forget_layers.py, scripts/raw_retention.py,
# tests/test_cold.py. Uses: nothing local.
import gzip
import json
import re
from datetime import datetime, timedelta

from pydantic import BaseModel

# Config
RAW_DAYS = 90  # docs: Starting numbers, "Raw retention"
RAW_PATH = re.compile(r"/raw/(\d{4})/(\d{2})/(\d{2})/")  # S1 stores raw/YYYY/MM/DD/<id>
TOMBSTONE_KIND = "raw_tombstone"


class RawTombstone(BaseModel):
    """All that is left of a raw body after its retention: where it was, when and why it went."""
    uri: str
    deleted_at: datetime
    reason: str


# --- Cold

def cold_uri(lane, item_id: str) -> str:
    return f"s3://brain/{lane.seed['tenant_id']}/cold/{item_id}.json.gz"


def freeze(lane, item_ids: list[str]) -> int:
    """Archive each item with its vector, then drop the vector. Archive first, so a crash between the two loses nothing."""
    frozen = 0
    for item_id in item_ids:
        found = lane.chunks.full(item_id)
        if found is None or found[1] is None:
            continue
        lane.object_store[cold_uri(lane, item_id)] = gzip.compress(json.dumps({"item": found[0], "embedding": found[1]}, default=str).encode())
        lane.chunks.set_vector(item_id, None)
        frozen += 1
    return frozen


def thaw(lane, item_ids: list[str]) -> int:
    """Give each item its vector back from the archive, then remove the archive copy."""
    thawed = 0
    for item_id in item_ids:
        try:
            archived = json.loads(gzip.decompress(lane.object_store[cold_uri(lane, item_id)]))
        except KeyError:
            continue  # never frozen, or already thawed
        lane.chunks.set_vector(item_id, archived["embedding"])
        del lane.object_store[cold_uri(lane, item_id)]
        thawed += 1
    return thawed


# --- Raw retention

def expired_raw(uris, now: datetime, days: int = RAW_DAYS) -> list[str]:
    """Raw bodies stored on a day more than `days` ago, read from their path."""
    cutoff = (now - timedelta(days=days)).date()
    dated = [(uri, RAW_PATH.search(uri)) for uri in uris]
    return sorted(uri for uri, day in dated if day and datetime(*map(int, day.groups())).date() < cutoff)


def sweep_raw(lane, apply: bool, by: str = "retention") -> dict:
    """Delete raw bodies past their retention (or, without apply, only say which). Each leaves a tombstone; the sweep is audited."""
    due = expired_raw(list(lane.object_store), lane.now)
    if not apply or not due:
        return {"due": len(due), "deleted": 0}
    for uri in due:
        del lane.object_store[uri]
        lane.records.save(TOMBSTONE_KIND, uri, RawTombstone(uri=uri, deleted_at=lane.now, reason=f"raw retention of {RAW_DAYS} days ended"))
    lane.audit.append(f"retention:{lane.now.isoformat()}", "retention.raw_deleted", {"by": by, "at": lane.now.isoformat(), "reason": f"{len(due)} raw bodies older than {RAW_DAYS} days"})
    return {"due": len(due), "deleted": len(due)}
