# test_hq2_seed.py: Finebase HQ-2's seed. The sample files match their generator, a second seed adds nothing, HQ-2 never touches
# Finebase HQ (its sample file, its Kafka topics, its Postgres rows), and the screens' data is there. The Postgres part skips when Docker is off.
# Uses: scripts/hq2_world.py, scripts/seed_hq2.py, app/api/hq.py, app/pipeline/store_postgres.py.
import json

import pytest

from app.api import hq, lists
from app.pipeline import store_postgres
from scripts import hq2_world, seed_hq2
from scripts.hq2_cast import PLATFORMS, TENANT_ID

# Config
SKIP_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="Postgres is not answering (backend/scripts/dev_up.sh)")
EXPECTED_MINIMUMS = {"documents": 40, "connections": 12, "facts": 6, "runs": 30, "chats": 8, "asks": 4}


@pytest.fixture
def hq2_lane(monkeypatch):
    monkeypatch.setattr(hq, "TENANT_FILE", "hq2_tenant.json")
    return seed_hq2.open_lane(frozenset())


def test_sample_files_match_their_generator():
    built = {"hq2_tenant.json": hq2_world.build_tenant(), "hq2_world.json": hq2_world.build_world(), "hq2_obligations.json": hq2_world.build_obligations(), "hq2_counts.json": hq2_world.build_counts()}
    for name, body in built.items():
        assert json.loads((hq2_world.SAMPLES / name).read_text()) == json.loads(json.dumps(body)), f"{name} is stale: run uv run python -m scripts.hq2_world"


def test_a_second_seed_adds_nothing(hq2_lane):
    first = seed_hq2.seed_all(hq2_lane)
    assert all(first[name] >= least for name, least in EXPECTED_MINIMUMS.items()), first
    assert set(seed_hq2.seed_all(hq2_lane).values()) == {0}


def test_every_platform_is_a_connection_a_sensor_and_a_source(hq2_lane):
    seed_hq2.seed_all(hq2_lane)
    sensors = {s["id"]: s for s in lists.sensors_view(hq2_lane, hq2_lane.hq, hq2_lane.now)}
    connections = {c["connection_id"] for c in hq2_lane.records.list_kind("connection")}
    sources = {item["platform"] for item in hq2_lane.graph.latest("knowledge") if item.get("platform")}
    for platform_id, *_ in PLATFORMS:
        assert f"conn_{platform_id}" in sensors and f"conn_{platform_id}" in connections and platform_id in sources, platform_id


def test_policies_have_a_dated_change_and_the_audit_chain_holds(hq2_lane):
    from app.pipeline.audit import verify_chain
    seed_hq2.seed_all(hq2_lane)
    spend = {item["version_ref"]["version"] for item in hq2_lane.graph.latest("knowledge") if item.get("version_ref") and item["version_ref"]["id"] == "policy_spend"}
    assert spend == {1, 2}
    assert verify_chain(hq2_lane.audit.in_order()) is None


def test_it_stays_apart_from_finebase_hq(monkeypatch):
    monkeypatch.setattr(hq, "TENANT_FILE", "hq_tenant.json")
    hq_seed, _ = hq.load_hq()
    monkeypatch.setattr(hq, "TENANT_FILE", "hq2_tenant.json")
    two_seed, _ = hq.load_hq()
    assert hq_seed["tenant_id"] == "finebase-hq" and two_seed["tenant_id"] == TENANT_ID
    assert hq.topic_prefix(hq_seed) == "" and hq.topic_prefix(two_seed) == f"{TENANT_ID}."  # HQ keeps its topics; HQ-2 has its own
    assert not {i["item_id"] for i in hq_seed["knowledge"]} & {i["item_id"] for i in two_seed["knowledge"] if i["item_id"].startswith(("doc_", "policy_"))}
    assert hq.SAMPLES.joinpath("hq_tenant.json").read_text().count("finebase-hq-2") == 0


@SKIP_POSTGRES
def test_on_postgres_it_is_idempotent_and_leaves_finebase_hq_alone(monkeypatch):
    monkeypatch.setattr(hq, "TENANT_FILE", "hq2_tenant.json")
    connection = store_postgres.connect()
    tables = [row[0] for row in connection.execute("SELECT table_name FROM information_schema.columns WHERE column_name = 'tenant_id' AND table_schema = 'public'")]
    rows_of = lambda tenant: {t: connection.execute(f"SELECT count(*) FROM {t} WHERE tenant_id = %s", (tenant,)).fetchone()[0] for t in tables}  # noqa: E731
    hq_before = rows_of("finebase-hq")
    seed_hq2.seed_all(seed_hq2.open_lane(frozenset({"postgres"})))
    mid = rows_of(TENANT_ID)
    again = seed_hq2.seed_all(seed_hq2.open_lane(frozenset({"postgres"})))
    assert set(again.values()) == {0} and rows_of(TENANT_ID) == mid
    assert rows_of("finebase-hq") == hq_before
    assert mid["records"] > 150 and mid["audit_log"] > 100 and mid["graph_nodes"] > 100


def test_reset_refuses_any_other_tenant():
    with pytest.raises(ValueError):
        seed_hq2.reset_tenant(None, "finebase-hq")
