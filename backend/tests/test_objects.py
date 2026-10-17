# test_objects.py: the same object store checks on a dict and on S3 (SeaweedFS locally), so both behave alike.
# S3 tests are skipped when nothing answers on localhost:9000 (start it with backend/infra/compose.yaml).
# Uses: app/pipeline/store_s3.py, app/pipeline/stages_intake.py, tests/golden.py.
import uuid

import pytest

from app.pipeline import fakes, stages_intake
from app.pipeline.store_s3 import S3_BUCKET, S3ObjectStore, connect, s3_is_up
from tests.golden import NOW, raw_sample

# Config
S3_UP = s3_is_up()
NEEDS_S3 = pytest.mark.skipif(not S3_UP, reason="no S3 endpoint on localhost:9000")


# --- Helpers

@pytest.fixture
def tenant() -> str:
    """A new tenant per test, so objects from earlier runs never show up."""
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture(params=["memory", "s3"])
def objects(request, tenant):
    if request.param == "memory":
        return {}
    if not S3_UP:
        pytest.skip("no S3 endpoint on localhost:9000")
    return S3ObjectStore(connect(), prefix=f"{tenant}/")


# --- On both

def test_written_body_reads_back(objects, tenant):
    uri = f"s3://{S3_BUCKET}/{tenant}/raw/2026/10/10/gmail_1.eml"
    objects[uri] = b"From: someone\n\nhello"
    assert (objects[uri], list(objects), len(objects)) == (b"From: someone\n\nhello", [uri], 1)


def test_missing_object_raises(objects, tenant):
    with pytest.raises(KeyError):
        objects[f"s3://{S3_BUCKET}/{tenant}/raw/missing.eml"]


def test_delete_removes(objects, tenant):
    uri = f"s3://{S3_BUCKET}/{tenant}/raw/old.eml"
    objects[uri] = b"old"
    del objects[uri]
    assert uri not in objects and len(objects) == 0


def test_s1_stores_and_s2_reads_back(objects, tenant):
    k1 = stages_intake.capture(raw_sample("s2"), tenant, objects, NOW)
    signal = stages_intake.normalize(k1, "evt_raw", tenant, objects, {}, set(), fakes.make_id_maker())
    assert objects[k1.raw_object_uri] == raw_sample("s2")["raw_body"].encode()
    assert signal.subject.entity_ref == "pay_FB_20261004_0192"


# --- S3 only

@NEEDS_S3
def test_other_buckets_are_refused(tenant):
    objects = S3ObjectStore(connect(), prefix=f"{tenant}/")
    with pytest.raises(KeyError):
        objects[f"s3://somebody_else/{tenant}/raw/x.eml"] = b"no"


@NEEDS_S3
def test_prefixes_never_mix():
    client = connect()
    ours, theirs = f"test_{uuid.uuid4().hex[:8]}", f"test_{uuid.uuid4().hex[:8]}"
    S3ObjectStore(client, prefix=f"{ours}/")[f"s3://{S3_BUCKET}/{ours}/raw/x.eml"] = b"ours"
    assert len(S3ObjectStore(client, prefix=f"{theirs}/")) == 0
