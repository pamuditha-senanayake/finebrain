# test_keyset.py: the same "seen before" checks on a Python set and on Valkey, so both behave alike.
# Valkey tests are skipped when nothing answers on localhost:6379 (start it with backend/infra/compose.yaml).
# Uses: app/pipeline/store_valkey.py, app/pipeline/stages_intake.py, tests/golden.py.
import uuid

import pytest

from app.pipeline import fakes, stages_intake
from app.pipeline.store_valkey import ValkeyKeySet, connect, valkey_is_up
from tests.golden import NOW, raw_sample

# Config
VALKEY_UP = valkey_is_up()
NEEDS_VALKEY = pytest.mark.skipif(not VALKEY_UP, reason="no Valkey on localhost:6379")
TENANT = "finebase_labs"


# --- Helpers

def fresh_namespace() -> str:
    """A new namespace per test, so tests never see each other's keys."""
    return f"test_{uuid.uuid4().hex[:8]}:s2_dedup"


@pytest.fixture(params=["memory", "valkey"])
def seen(request):
    if request.param == "memory":
        return set()
    if not VALKEY_UP:
        pytest.skip("no Valkey on localhost:6379")
    return ValkeyKeySet(connect(), fresh_namespace())


def normalize(key: str, store: dict, seen_keys) -> object:
    """S1 then S2 on one raw sample, sharing a dedup key set."""
    k1 = stages_intake.capture(raw_sample(key), TENANT, store, NOW)
    return stages_intake.normalize(k1, "evt_raw", TENANT, store, {}, seen_keys, fakes.make_id_maker())


# --- On both

def test_added_member_is_seen(seen):
    seen.add("finebase_labs:email:gmail_1")
    seen.add("finebase_labs:email:gmail_1")
    assert "finebase_labs:email:gmail_1" in seen and "finebase_labs:email:gmail_2" not in seen
    assert (len(seen), sorted(seen)) == (1, ["finebase_labs:email:gmail_1"])


def test_discard_forgets(seen):
    seen.add("key_a")
    seen.discard("key_a")
    assert "key_a" not in seen and len(seen) == 0


def test_s2_drops_the_redelivered_email(seen):
    store = {}
    first = normalize("s2", store, seen)
    redelivered = normalize("s5", store, seen)
    assert first is not None and redelivered is None
    assert first.dedup_key in seen


# --- Valkey only

@NEEDS_VALKEY
def test_members_expire():
    client = connect()
    seen = ValkeyKeySet(client, fresh_namespace(), ttl_seconds=60)
    seen.add("key_a")
    assert 0 < client.ttl(seen.key_for("key_a")) <= 60


@NEEDS_VALKEY
def test_only_the_first_claim_wins():
    seen = ValkeyKeySet(connect(), fresh_namespace())
    assert [seen.claim("evt_0001") for _ in range(3)] == [True, False, False]


@NEEDS_VALKEY
def test_namespaces_never_mix():
    client = connect()
    ours, theirs = ValkeyKeySet(client, fresh_namespace()), ValkeyKeySet(client, fresh_namespace())
    ours.add("key_a")
    assert "key_a" not in theirs and len(theirs) == 0
