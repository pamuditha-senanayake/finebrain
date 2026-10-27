# pack_store.py: where accepted packs live. The row (manifest, audit, who, when) in research.packs; the zip itself in S3
# under research/packs/<sha256>.zip, written first so a row never points at a missing file. The same pack uploaded twice
# is one pack: the hash is unique. PostgresPacks and its memory twin. Used by: research/routes.py. Uses: research/contracts.py.
import uuid
from collections.abc import MutableMapping

import psycopg
from psycopg.types.json import Jsonb

from app.research.contracts import Pack

# Config
RECENT_LIMIT = 50
COLUMNS = "id, kind, name, version, sha256, manifest, audit, uploaded_by, uploaded_at"


def blob_uri(sha: str) -> str:
    return f"s3://brain/research/packs/{sha}.zip"


def new_pack(kind: str, manifest: dict, sha: str, audit: dict, uploaded_by: str) -> Pack:
    return Pack(id=str(uuid.uuid4()), kind=kind, name=manifest["name"], version=manifest["version"], sha256=sha,
                manifest=manifest, audit=audit, uploaded_by=uploaded_by)


class MemoryPacks:
    """The in-memory twin of PostgresPacks."""

    def __init__(self):
        self.rows: dict[str, Pack] = {}
        self.blobs: dict[str, bytes] = {}

    def save(self, pack: Pack, data: bytes) -> tuple[Pack, bool]:
        """The stored pack, and whether this call stored it (False: the same pack was already there)."""
        existing = next((p for p in self.rows.values() if p.sha256 == pack.sha256), None)
        if existing:
            return existing, False
        self.blobs[blob_uri(pack.sha256)] = data
        self.rows[pack.id] = pack
        return pack, True

    def get(self, pack_id: str) -> Pack | None:
        return self.rows.get(pack_id)

    def recent(self, limit: int = RECENT_LIMIT) -> list[Pack]:
        return list(reversed(self.rows.values()))[:limit]

    def zip_of(self, pack: Pack) -> bytes:
        return self.blobs[blob_uri(pack.sha256)]


class PostgresPacks:
    """Rows in research.packs, zips in S3. Same answers as MemoryPacks."""

    def __init__(self, connection: psycopg.Connection, blobs: MutableMapping[str, bytes]):
        self.connection, self.blobs = connection, blobs

    def save(self, pack: Pack, data: bytes) -> tuple[Pack, bool]:
        # Step 1: the zip first, under its hash, so the same pack always lands on the same object
        self.blobs[blob_uri(pack.sha256)] = data

        # Step 2: the row; two uploads of one pack at once insert one row, and the other reads it back
        inserted = self.connection.execute(
            f"""INSERT INTO research.packs ({COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (sha256) DO NOTHING RETURNING {COLUMNS}""",
            (pack.id, pack.kind, pack.name, pack.version, pack.sha256, Jsonb(pack.manifest), Jsonb(pack.audit), pack.uploaded_by)).fetchone()
        if inserted:
            return as_pack(inserted), True
        return as_pack(self.connection.execute(f"SELECT {COLUMNS} FROM research.packs WHERE sha256 = %s", (pack.sha256,)).fetchone()), False

    def get(self, pack_id: str) -> Pack | None:
        if not is_uuid(pack_id):
            return None
        row = self.connection.execute(f"SELECT {COLUMNS} FROM research.packs WHERE id = %s", (pack_id,)).fetchone()
        return as_pack(row) if row else None

    def recent(self, limit: int = RECENT_LIMIT) -> list[Pack]:
        rows = self.connection.execute(f"SELECT {COLUMNS} FROM research.packs ORDER BY uploaded_at DESC LIMIT %s", (limit,))
        return [as_pack(row) for row in rows]

    def zip_of(self, pack: Pack) -> bytes:
        return self.blobs[blob_uri(pack.sha256)]


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def as_pack(row: tuple) -> Pack:
    pack_id, kind, name, version, sha, manifest, audit, uploaded_by, uploaded_at = row
    return Pack(id=str(pack_id), kind=kind, name=name, version=version, sha256=sha, manifest=manifest, audit=audit,
                uploaded_by=uploaded_by, uploaded_at=uploaded_at.isoformat())
