# lists_query.py: step 12, lists of thousands. The server filters, searches, sorts and pages, so the browser never holds
# the whole list. One call returns a page, the total, where a target row sits, which rows match the search, and the
# count behind every filter value. Used by: routes.py. Uses: lists_rows.py.
# `q` finds rows without hiding the rest (the console steps through the matches); filters narrow the list.
from dataclasses import dataclass

from app.api import lists_rows

# Config
PAGE = 100
MOST = 500
MOST_MATCHES = 5000


@dataclass
class Spec:
    rows: object  # lane -> list of the console's row shapes, in their default order
    texts: tuple[str, ...]  # row fields the search reads
    facets: tuple[str, ...]  # row fields a person can filter by


LISTS = {
    "runs": Spec(lists_rows.runs, ("subject", "id", "agentId", "status"), ("status", "agentId", "clusterId")),
    "escalations": Spec(lists_rows.escalations, ("subject", "id", "agentId"), ("status", "agentId", "clusterId")),
    "access-decisions": Spec(lists_rows.access, ("principal", "action", "resource", "reason", "ruleId"), ("decision", "principal")),
    "audit": Spec(lists_rows.audit, ("action", "detail"), ("action", "criticality")),
    "documents": Spec(lists_rows.docs, ("title", "type"), ("sensitivity", "type", "extractionStatus")),
}


def chosen(spec: Spec, query: dict) -> dict[str, set[str]]:
    """The filters the caller set: a field and the values it may hold (comma separated)."""
    return {field: set(query[field].split(",")) for field in spec.facets if query.get(field)}


def keep(row: dict, filters: dict[str, set[str]], skip: str | None = None) -> bool:
    return all(str(row.get(field)) in values for field, values in filters.items() if field != skip)


def matches(row: dict, spec: Spec, words: list[str]) -> bool:
    text = " ".join(str(row.get(field, "")) for field in spec.texts).lower()
    return all(word in text for word in words)


def counts(rows: list[dict], field: str, filters: dict[str, set[str]]) -> dict[str, int]:
    """How many rows each value of `field` would give, with every other filter applied."""
    found: dict[str, int] = {}
    for row in rows:
        if keep(row, filters, skip=field):
            found[str(row.get(field))] = found.get(str(row.get(field)), 0) + 1
    return found


def sorted_by(rows: list[dict], sort: str) -> list[dict]:
    """`field:asc` or `field:desc`. Without it the list keeps its own order (newest first)."""
    field, _, direction = sort.partition(":")
    return sorted(rows, key=lambda row: (row.get(field) is None, row.get(field)), reverse=direction == "desc") if field else rows


def page(lane, name: str, query: dict) -> dict | None:
    """One page of a served list, or None when the list is not served. `around` is a row id to land on."""
    spec = LISTS.get(name)
    if spec is None:
        return None
    filters = chosen(spec, query)
    everything = spec.rows(lane)
    rows = sorted_by([row for row in everything if keep(row, filters)], query.get("sort", ""))
    size = min(int(query.get("limit") or PAGE), MOST)
    position = next((index for index, row in enumerate(rows) if row["id"] == query.get("around")), None) if query.get("around") else None
    offset = (position // size) * size if position is not None else int(query.get("offset") or 0)
    words = (query.get("q") or "").lower().split()
    found = [index for index, row in enumerate(rows) if matches(row, spec, words)][:MOST_MATCHES] if words else []
    return {"items": rows[offset:offset + size], "offset": offset, "total": len(rows), "position": position,
            "facets": {field: counts(everything, field, filters) for field in spec.facets}, "matches": {"total": len(found), "positions": found}}
