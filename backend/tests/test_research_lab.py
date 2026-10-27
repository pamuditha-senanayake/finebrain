# test_research_lab.py: the lab tenant (Research Lab step 3). A lab runs the real pipeline on its own tenant, topics, object
# prefix, keys and shop, acts only in shadow, and leaves nothing behind after teardown. Lab code refuses any other tenant.
# Real-infra tests skip when Docker is off. Uses: research/lab_tenant.py, research/lab_shop.py, tests/s6_world.py, tests/s7_world.py.
import json
import threading
import uuid

import psycopg
import pytest
from confluent_kafka.admin import AdminClient

from app.pipeline import conn_call, kafka_admin, orchestrate, store_postgres, store_s3, tool_runners
from app.pipeline.adapters import missing_infra
from app.research import lab_shop, lab_tenant
from scripts import shop_db
from tests.golden import NOW
from tests.s5_world import world_seed
from tests.s6_world import ask, refund, scripted
from tests.s7_world import last_record, says
from tests.test_s1_refund_chat import FIRST, SECOND
from tests.test_s9_real import brain_refunds, order_status

NEEDS_LAB_INFRA = pytest.mark.skipif(bool(missing_infra(lab_tenant.LAB_PARTS)), reason="lab infra not answering")


def new_lab_id() -> str:
    return lab_tenant.lab_id_for(str(uuid.uuid4()))


def anna_lab(lab_id: str):
    """A lab on real infra with the sample shop, where Anna asks for her refund in two visits."""
    lane = lab_tenant.create_lab(lab_id, world_seed(), scripted(ask(), refund())[0], NOW, shop=shop_db.WORLD)
    says(lane, FIRST)
    says(lane, SECOND)
    return lane


# --- Only lab ids

@pytest.mark.parametrize("tenant", ["finebase-hq", "test_abc", "lab_", "lab_XYZ", "lab_" + "0" * 31, "", "lab_" + "0" * 32 + "; DROP"])
def test_lab_code_refuses_any_other_tenant(tenant):
    for call in (lambda: lab_tenant.create_lab(tenant, world_seed(), None, NOW, parts=frozenset()), lambda: lab_tenant.teardown(tenant),
                 lambda: lab_tenant.leftovers(tenant), lambda: lab_tenant.topic_prefix(tenant)):
        with pytest.raises(lab_tenant.NotALab):
            call()


def test_a_lab_in_memory_runs_on_its_own_tenant_in_shadow_and_without_a_shop_escalates():
    lab_id = new_lab_id()
    lane = lab_tenant.create_lab(lab_id, world_seed(), scripted(ask())[0], NOW, parts=frozenset())
    assert lane.seed["tenant_id"] == lab_id and not tool_runners.is_live(lane.tooling) and lane.tooling["send_email"] is None
    says(lane, FIRST)
    assert last_record(lane)["outcome"] == "escalated"  # no orders to confirm: a person, never a guess
    assert lane.bus.topics["runs.completed"][-1].tenant_id == lab_id


def test_a_missing_part_is_refused_not_quietly_swapped_for_memory(monkeypatch):
    monkeypatch.setattr(lab_tenant, "missing_infra", lambda parts: ["kafka"])
    with pytest.raises(lab_tenant.LabInfraMissing, match="kafka"):
        lab_tenant.create_lab(new_lab_id(), world_seed(), None, NOW)


# --- Real infra: the whole lab, then nothing

@NEEDS_LAB_INFRA
def test_anna_in_a_lab_runs_for_real_stays_in_the_lab_and_teardown_leaves_nothing():
    lab_id = new_lab_id()
    shop_db.setup()
    test_shop_before = (brain_refunds(), order_status())
    try:
        lane = anna_lab(lab_id)

        # Step 1: the real pipeline decided as in production, with the payment read from the lab's own shop
        record = last_record(lane)
        assert (record["outcome"], record["decided_by"]) == ("resolved", "auto by policy")
        refund_call = lane.records.load(tool_runners.SHADOW_KIND, lane.bus.topics["actions.executed"][-1].payload["idempotency_key"])
        assert refund_call["arguments"]["payment_ref"] == "pay_FB_20260930_0144"

        # Step 2: nothing reached a shop: the lab's shop holds only the pack's rows, the test shop is untouched
        with psycopg.connect(lab_shop.server_url(lab_shop.LAB_SHOP_DB)) as shop:
            assert shop.execute(f"SELECT count(*) FROM {lab_id}.refunds").fetchone()[0] == len(shop_db.WORLD["refunds"])
        assert (brain_refunds(), order_status()) == test_shop_before

        # Step 3: the lab's traces sit under its prefix, its messages on its own topics, and no other tenant's rows name it
        assert record["trace_object_uri"] in lane.object_store
        assert lane.object_store.key_for(record["trace_object_uri"]).startswith(lab_tenant.object_prefix(lab_id))
        topics = AdminClient({"bootstrap.servers": kafka_admin.DEFAULT_BOOTSTRAP}).list_topics(timeout=10).topics
        assert f"lab.{lab_id}.runs.completed" in topics
        with store_postgres.connect() as connection:
            named = connection.execute("SELECT count(*) FROM records WHERE tenant_id <> %s AND body::text LIKE %s", (lab_id, f"%{lab_id}%")).fetchone()[0]
        assert named == 0
        assert all(n > 0 for name, n in lab_tenant.leftovers(lab_id).items() if name in ("postgres", "s3", "kafka", "shop"))
        lab_tenant.close_lab(lane)

        # Step 4: teardown removes it from every store, and a second teardown finds nothing to do
        receipt = lab_tenant.teardown(lab_id)
        assert receipt["complete"], receipt
        assert lab_tenant.teardown(lab_id)["complete"] and set(lab_tenant.leftovers(lab_id).values()) == {0}
    finally:
        lab_tenant.teardown(lab_id)


@NEEDS_LAB_INFRA
def test_the_lab_shop_user_reads_its_own_schema_only():
    first, second = new_lab_id(), new_lab_id()
    try:
        lanes = [lab_tenant.create_lab(lab_id, world_seed(), None, NOW, shop=shop_db.WORLD) for lab_id in (first, second)]
        address = conn_call.get_secret(lanes[0], lab_tenant.SHOP_CONNECTION, "database_url")
        with psycopg.connect(address, autocommit=True) as reader:
            assert reader.execute(f"SELECT count(*) FROM {first}.orders").fetchone()[0] == len(shop_db.WORLD["orders"])
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                reader.execute(f"SELECT count(*) FROM {second}.orders")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                reader.execute(f"INSERT INTO {first}.refunds VALUES ('RF-X', 'ORD-1002', 1, 'approved', now())")
        for lane in lanes:
            lab_tenant.close_lab(lane)
    finally:
        assert lab_tenant.teardown(first)["complete"] and lab_tenant.teardown(second)["complete"]


@NEEDS_LAB_INFRA
def test_two_labs_built_at_once_stay_apart_and_the_same_lab_built_twice_is_one_lab():
    lab_ids = [new_lab_id(), new_lab_id()]
    errors: list[Exception] = []

    def build(lab_id: str) -> None:
        try:
            lab_tenant.close_lab(lab_tenant.create_lab(lab_id, world_seed(), None, NOW, shop=shop_db.WORLD))
        except Exception as error:  # collected, so the test names it instead of a thread swallowing it
            errors.append(error)

    try:
        workers = [threading.Thread(target=build, args=(lab_id,)) for lab_id in [*lab_ids, lab_ids[0]]]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert errors == []
        with psycopg.connect(lab_shop.server_url(lab_shop.LAB_SHOP_DB)) as shop:
            assert shop.execute(f"SELECT count(*) FROM {lab_ids[0]}.orders").fetchone()[0] == len(shop_db.WORLD["orders"])  # loaded once
    finally:
        assert all(lab_tenant.teardown(lab_id)["complete"] for lab_id in lab_ids)


# --- Teardown failures

@NEEDS_LAB_INFRA
def test_a_teardown_that_crashed_halfway_is_finished_by_the_next():
    lab_id = new_lab_id()
    lab_tenant.close_lab(anna_lab(lab_id))
    lab_tenant.postgres_rows(lab_id, apply=True)  # the crash: only Postgres was cleared
    assert lab_tenant.leftovers(lab_id)["postgres"] == 0 and lab_tenant.leftovers(lab_id)["shop"] > 0
    assert lab_tenant.teardown(lab_id)["complete"]


@NEEDS_LAB_INFRA
def test_a_store_that_does_not_answer_leaves_teardown_incomplete(monkeypatch):
    lab_id = new_lab_id()
    lab_tenant.close_lab(anna_lab(lab_id))
    monkeypatch.setitem(lab_tenant.STORES, "s3", (lambda: False, lab_tenant.s3_objects))
    receipt = lab_tenant.teardown(lab_id)
    assert not receipt["complete"] and receipt["left"]["s3"] is None  # unknown, never reported as clean
    monkeypatch.undo()
    assert lab_tenant.teardown(lab_id)["complete"]
