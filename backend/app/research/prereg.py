# prereg.py: preregistrations. A draft can change; locking stamps who, when and the sha256 of the paper, title and
# hypotheses, and from then on nothing can change it (the database trigger in store.py refuses it too). Two people locking
# at once: one wins, the other is told it is already locked. PostgresPreregs and its memory twin.
# Used by: research/prereg_routes.py, research/runner.py. Uses: research/contracts.py.
import hashlib
import json
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.types.json import Jsonb

from app.research.contracts import Hypothesis, Preregistration

# Config
COLUMNS = "id, paper, title, hypotheses, sha256, locked_at, locked_by"
RECENT_LIMIT = 50


class PreregLocked(Exception):
    """The preregistration is locked: its thresholds can never change."""


def fingerprint(paper: str, title: str, hypotheses: list[Hypothesis]) -> str:
    """sha256 of the canonical JSON, so the same words always give the same hash and any change gives another."""
    body = {"paper": paper, "title": title, "hypotheses": [h.model_dump(mode="json") for h in hypotheses]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def problems(hypotheses: list[Hypothesis]) -> list[str]:
    """What the field types cannot say: at least one hypothesis, and each id once."""
    ids = [h.id for h in hypotheses]
    return (["at least one hypothesis is needed"] if not ids else []) + [f"{i}: used twice" for i in sorted(set(ids)) if ids.count(i) > 1]


def draft(paper: str, title: str, hypotheses: list[Hypothesis]) -> Preregistration:
    return Preregistration(id=str(uuid.uuid4()), paper=paper, title=title, hypotheses=hypotheses, sha256=fingerprint(paper, title, hypotheses))


def holds(prereg: Preregistration) -> bool:
    """True when the stored hash still matches the words: the runner checks it before every run."""
    return prereg.sha256 == fingerprint(prereg.paper, prereg.title, prereg.hypotheses)


class MemoryPreregs:
    """The in-memory twin of PostgresPreregs."""

    def __init__(self):
        self.rows: dict[str, Preregistration] = {}

    def create(self, prereg: Preregistration) -> Preregistration:
        self.rows[prereg.id] = prereg
        return prereg

    def get(self, prereg_id: str) -> Preregistration | None:
        return self.rows.get(prereg_id)

    def recent(self, limit: int = RECENT_LIMIT) -> list[Preregistration]:
        return list(reversed(self.rows.values()))[:limit]

    def edit(self, prereg_id: str, title: str, hypotheses: list[Hypothesis]) -> Preregistration | None:
        current = self.rows.get(prereg_id)
        if current is None:
            return None
        if current.locked_at:
            raise PreregLocked(prereg_id)
        self.rows[prereg_id] = current.model_copy(update={"title": title, "hypotheses": hypotheses, "sha256": fingerprint(current.paper, title, hypotheses)})
        return self.rows[prereg_id]

    def lock(self, prereg_id: str, person: str) -> Preregistration | None:
        current = self.rows.get(prereg_id)
        if current is None:
            return None
        if current.locked_at:
            raise PreregLocked(prereg_id)
        self.rows[prereg_id] = current.model_copy(update={"locked_at": datetime.now(timezone.utc).isoformat(), "locked_by": person})
        return self.rows[prereg_id]


class PostgresPreregs:
    """Rows in research.preregistrations. Same answers as MemoryPreregs."""

    def __init__(self, connection: psycopg.Connection):
        self.connection = connection

    def create(self, prereg: Preregistration) -> Preregistration:
        row = self.connection.execute(f"INSERT INTO research.preregistrations ({COLUMNS}) VALUES (%s, %s, %s, %s, %s, NULL, NULL) RETURNING {COLUMNS}",
                                      (prereg.id, prereg.paper, prereg.title, Jsonb([h.model_dump(mode="json") for h in prereg.hypotheses]), prereg.sha256)).fetchone()
        return as_prereg(row)

    def get(self, prereg_id: str) -> Preregistration | None:
        if not is_uuid(prereg_id):
            return None
        row = self.connection.execute(f"SELECT {COLUMNS} FROM research.preregistrations WHERE id = %s", (prereg_id,)).fetchone()
        return as_prereg(row) if row else None

    def recent(self, limit: int = RECENT_LIMIT) -> list[Preregistration]:
        rows = self.connection.execute(f"SELECT {COLUMNS} FROM research.preregistrations ORDER BY locked_at DESC NULLS FIRST, id LIMIT %s", (limit,))
        return [as_prereg(row) for row in rows]

    def edit(self, prereg_id: str, title: str, hypotheses: list[Hypothesis]) -> Preregistration | None:
        current = self.get(prereg_id)
        if current is None:
            return None
        row = self.connection.execute(
            f"UPDATE research.preregistrations SET title = %s, hypotheses = %s, sha256 = %s WHERE id = %s AND locked_at IS NULL RETURNING {COLUMNS}",
            (title, Jsonb([h.model_dump(mode="json") for h in hypotheses]), fingerprint(current.paper, title, hypotheses), prereg_id)).fetchone()
        if row is None:
            raise PreregLocked(prereg_id)
        return as_prereg(row)

    def lock(self, prereg_id: str, person: str) -> Preregistration | None:
        """One statement, so of two people locking at once exactly one gets the row back."""
        if self.get(prereg_id) is None:
            return None
        row = self.connection.execute(f"UPDATE research.preregistrations SET locked_at = now(), locked_by = %s WHERE id = %s AND locked_at IS NULL RETURNING {COLUMNS}",
                                      (person, prereg_id)).fetchone()
        if row is None:
            raise PreregLocked(prereg_id)
        return as_prereg(row)


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def as_prereg(row: tuple) -> Preregistration:
    prereg_id, paper, title, hypotheses, sha, locked_at, locked_by = row
    return Preregistration(id=str(prereg_id), paper=paper, title=title, hypotheses=hypotheses, sha256=sha,
                           locked_at=locked_at.isoformat() if locked_at else None, locked_by=locked_by)
