# test_research_pack_api.py: uploading packs to the Lab (Research Lab step 4). A pack that fails an audit is refused with
# every audit shown; a warning needs a typed reason; a good pack is kept once, however often it is sent; a store that does
# not answer is a 503, never a lost pack. Real Postgres and S3 when Docker is up. Uses: research/routes.py,
# research/pack_routes.py, research/pack_store.py, tests/research_packs_world.py, tests/test_research_api.py (people).
import json
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from app.pipeline import store_postgres, store_s3
from app.research import pack_store, packs, store
from app.research.routes import create_research_app
from tests.research_packs_world import document, files, manifest_with, zipped
from tests.test_research_api import PEOPLE, FakeConnection

# Config
FOUNDER = {"x-persona": "h-founder"}
NEEDS_STORES = pytest.mark.skipif(not (store_postgres.database_is_up() and store_s3.s3_is_up()), reason="Postgres or S3 not answering")


def memory_client() -> tuple[TestClient, pack_store.MemoryPacks]:
    packs = pack_store.MemoryPacks()
    return TestClient(create_research_app(connect=FakeConnection, people=PEOPLE, make_packs=lambda connection: packs)), packs


def upload(client: TestClient, data: bytes, reasons: dict | None = None, headers: dict = FOUNDER):
    return client.post("/packs", files={"file": ("pack.zip", data, "application/zip")}, data={"reasons": json.dumps(reasons or {})}, headers=headers)


# --- Each answer the upload can give

def test_only_the_founder_or_the_research_role_may_upload():
    client, _ = memory_client()
    assert upload(client, zipped(files()), headers={}).status_code == 401
    assert upload(client, zipped(files()), headers={"x-persona": "h-steward"}).status_code == 403


def test_a_good_pack_is_kept_once_and_can_be_read_back():
    client, packs = memory_client()
    first = upload(client, zipped(files()))
    assert first.status_code == 201 and first.json()["created"]
    again = upload(client, zipped(files(), folder="copy/", crlf=True))  # the same pack, zipped differently
    assert again.status_code == 200 and again.json()["pack"]["id"] == first.json()["pack"]["id"]
    pack = first.json()["pack"]
    assert (pack["kind"], pack["name"], pack["uploadedBy"], pack["audit"]["verdict"]) == ("freshness", "tiny_freshness", "h-founder", "pass")
    assert client.get(f"/packs/{pack['id']}", headers=FOUNDER).json()["sha256"] == pack["sha256"]
    assert [p["id"] for p in client.get("/packs", headers=FOUNDER).json()] == [pack["id"]]
    assert len(packs.blobs) == 1


def test_a_failing_pack_is_refused_with_every_audit_and_nothing_is_kept():
    client, packs = memory_client()
    leaking = files(**{"documents/UPD-F01.md": document("UPD-F01", "It replaces the earlier value.", supersedes="POL-001")})
    answer = upload(client, zipped(leaking))
    assert answer.status_code == 422 and answer.json()["error"] == "pack_failed_audits"
    assert {a["key"]: a["status"] for a in answer.json()["audits"]}["marker_leak"] == "fail" and len(answer.json()["audits"]) == 10
    assert packs.rows == {} and packs.blobs == {}


def test_a_warning_needs_a_typed_reason_and_the_reason_is_kept():
    client, _ = memory_client()
    data = zipped(files(**{"manifest.json": manifest_with(exposure_check=None)}))
    asked = upload(client, data)
    assert asked.status_code == 409 and asked.json()["needs"] == ["exposure"]
    assert upload(client, data, {"exposure": "   "}).status_code == 409  # blank is not a reason
    kept = upload(client, data, {"exposure": "Fictional name, checked by hand on 27 October"})
    assert kept.status_code == 201 and kept.json()["pack"]["audit"]["reasons"] == {"exposure": "Fictional name, checked by hand on 27 October"}


def test_unreadable_uploads_and_bad_reasons_say_why():
    client, _ = memory_client()
    assert upload(client, b"plain text").json() == {"error": "not_a_zip"}
    assert upload(client, zipped({"../x": "y"})).json()["error"].startswith("unsafe_path")
    bad = client.post("/packs", files={"file": ("p.zip", zipped(files()), "application/zip")}, data={"reasons": "[1, 2]"}, headers=FOUNDER)
    assert bad.status_code == 400 and bad.json() == {"error": "bad_reasons"}
    assert client.get("/packs/nope", headers=FOUNDER).status_code == 404


def test_a_store_that_does_not_answer_is_a_503():
    def broken(connection):
        raise store_postgres.psycopg.OperationalError("down")

    client = TestClient(create_research_app(connect=FakeConnection, people=PEOPLE, make_packs=broken))
    answer = upload(client, zipped(files()))
    assert answer.status_code == 503 and answer.json() == {"error": "research_store_unavailable"}


# --- Real Postgres and S3

@NEEDS_STORES
def test_on_real_postgres_and_s3_a_pack_is_kept_and_four_workers_at_once_keep_it_once():
    data = zipped(files(**{"README.md": f"Race test {uuid.uuid4()}\n"}))  # a pack no other test uses
    try:
        # Step 1: through the API, the zip lands in S3 and the row in Postgres
        answer = upload(TestClient(create_research_app(people=PEOPLE)), data)
        assert answer.status_code == 201
        sha = answer.json()["pack"]["sha256"]
        connection = store.connect()
        stored = pack_store.PostgresPacks(connection, store_s3.S3ObjectStore(store_s3.connect()))
        assert stored.zip_of(stored.get(answer.json()["pack"]["id"])) == data
        connection.execute("DELETE FROM research.packs WHERE sha256 = %s", (sha,))

        # Step 2: four workers, each with its own connection, save the same pack at once: one row, one id for all
        saved: list = []

        def save() -> None:
            with store.connect() as own:
                pack = pack_store.new_pack("freshness", {"name": "race", "version": "1"}, sha, {"verdict": "pass"}, "h-founder")
                saved.append(pack_store.PostgresPacks(own, store_s3.S3ObjectStore(store_s3.connect())).save(pack, data))

        workers = [threading.Thread(target=save) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert sorted(created for _, created in saved) == [False, False, False, True] and len({pack.id for pack, _ in saved}) == 1
    finally:
        with store.connect() as cleanup:
            cleanup.execute("DELETE FROM research.packs WHERE sha256 = %s", (packs_sha(data),))
        store_s3.connect().delete_object(Bucket=store_s3.S3_BUCKET, Key=f"research/packs/{packs_sha(data)}.zip")


def packs_sha(data: bytes) -> str:
    return packs.pack_hash(packs.read_zip(data))
