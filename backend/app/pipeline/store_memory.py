# store_memory.py: MemoryRecords, the in-memory twin of PostgresRecords. The vault's twin is a plain dict.
# Used by: tests/test_store.py, orchestrate.py from step 6. Uses: nothing local.
from pydantic import BaseModel


class MemoryRecords:
    """Append-only, like PostgresRecords: saving the same id again adds a version."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.versions: dict[tuple[str, str], list[dict]] = {}
        self.ids_by_kind: dict[str, set[str]] = {}  # so listing one kind never walks every record, like Postgres's index

    def save(self, kind: str, record_id: str, body: BaseModel) -> int:
        """Store a new version and return its number."""
        history = self.versions.setdefault((kind, record_id), [])
        history.append(body.model_dump(mode="json"))
        self.ids_by_kind.setdefault(kind, set()).add(record_id)
        return len(history)

    def load(self, kind: str, record_id: str) -> dict | None:
        """The latest version, or None when there is none."""
        history = self.history(kind, record_id)
        return history[-1] if history else None

    def history(self, kind: str, record_id: str) -> list[dict]:
        """Every version, oldest first."""
        return list(self.versions.get((kind, record_id), []))

    def list_kind(self, kind: str) -> list[dict]:
        """The latest version of every record of one kind, ordered by id like Postgres."""
        return [self.versions[(kind, record_id)][-1] for record_id in sorted(self.ids_by_kind.get(kind, ())) if (kind, record_id) in self.versions]

    def purge(self, kind: str, record_id: str) -> list[dict]:
        """Erase every version of one record and return what it held, so the caller can save a scrubbed copy."""
        return self.versions.pop((kind, record_id), [])
