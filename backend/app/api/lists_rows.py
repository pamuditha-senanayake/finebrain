# lists_rows.py: the rows the paged lists (lists_query.py) and search read: runs, escalations, access decisions, audit,
# documents. Each row is the console's own shape, built once and kept: a run is rebuilt only when it changed, and an
# audit entry never changes, so ten thousand of them cost one pass, not one per request.
# Used by: lists_query.py, search.py. Uses: views.py, documents.py.
from app.api import documents, views

# Config
ESCALATED = ("escalated", "awaiting_approval")


def cache_of(lane) -> dict:
    """Row caches live on the lane, so each pipeline keeps its own."""
    return lane.__dict__.setdefault("row_cache", {"runs": {}, "access": {}, "audit": {}})


def runs(lane) -> list[dict]:
    """Every run, newest first. A run is rebuilt when its outcome or steps changed since the last call."""
    kept, rows = cache_of(lane)["runs"], []
    for run in lane.records.list_kind("run"):
        steps = run["steps"]
        signature = (run["outcome"], len(steps), steps[-1]["started_at"] if steps else "")
        cached = kept.get(run["run_id"])
        if cached is None or cached[0] != signature:
            cached = kept[run["run_id"]] = (signature, views.run_view(lane, run).ui())
        rows.append(cached[1])
    return sorted(rows, key=lambda row: row["startedAt"], reverse=True)


def escalations(lane) -> list[dict]:
    return [row for row in runs(lane) if row["status"] in ESCALATED]


def audit_rows(lane, topic: str | None, make, kept_as: str) -> list[dict]:
    """Audit entries are append only, so each is converted once and found again by its seq."""
    kept = cache_of(lane)[kept_as]
    for entry in lane.audit.in_order():
        if (topic is None or entry["topic"] == topic) and entry["seq"] not in kept:
            kept[entry["seq"]] = make(lane, entry).ui()
    return [kept[seq] for seq in sorted(kept, reverse=True)]


def access(lane) -> list[dict]:
    return audit_rows(lane, "access.decisions", views.access_view, "access")


def audit(lane) -> list[dict]:
    return audit_rows(lane, None, views.audit_view, "audit")


def docs(lane) -> list[dict]:
    return documents.documents_view(lane)
