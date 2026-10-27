# lab_tenant.py: a throwaway tenant where the Lab runs the real pipeline. Its id is lab_<experiment hex>, so no product query
# ever matches it; its tools run in shadow mode; its messages go on lab.<id>.* topics, its objects and keys under its id
# (S3 keys come from each object's s3://brain/<tenant>/ address), and its shop in a schema of its own. Teardown removes all of it and checks that nothing is left.
# Every function refuses an id that is not a lab id. Used by: the Lab runner (step 6), tests/test_research_lab.py.
# Uses: orchestrate.py, adapters.py, conn_call.py, kafka_admin.py, store_postgres.py, store_s3.py, store_valkey.py, research/lab_shop.py.
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime

import psycopg
from confluent_kafka.admin import AdminClient

from app.pipeline import conn_call, kafka_admin, orchestrate, store_postgres, store_s3, store_valkey
from app.pipeline.adapters import make_memory_adapters, missing_infra, real_adapters
from app.pipeline.conn_call import Connection
from app.pipeline.conn_spec import DatabaseSpec
from app.research import lab_shop

# Config
LAB_ID = re.compile(r"^lab_[0-9a-f]{32}$")  # also safe as a Postgres name, a Kafka prefix and a key prefix
LAB_PARTS = frozenset({"postgres", "valkey", "s3", "kafka", "opa"})  # Temporal waits on real time, so lab lanes run in process
SHOP_CONNECTION = "conn_lab_shop"
BUILD_LOCK = 72_000_002  # advisory lock id: the product's stores set up their tables on connect, and two at once can deadlock
BUILDING = threading.Lock()  # the same within one process, where conditions build in parallel threads (the shop is always a Postgres schema)


class NotALab(ValueError):
    """Lab code was handed an id that is not a lab tenant. Nothing was touched."""


class LabInfraMissing(RuntimeError):
    """A part the lab was asked to run on does not answer. The lab never falls back to memory without saying so."""


def lab_id_for(experiment_id: str) -> str:
    return f"lab_{uuid.UUID(experiment_id).hex}"


def checked(lab_id: str) -> str:
    if not LAB_ID.match(lab_id or ""):
        raise NotALab(lab_id)
    return lab_id


def topic_prefix(lab_id: str) -> str:
    return f"lab.{checked(lab_id)}."


def object_prefix(lab_id: str) -> str:
    return f"{checked(lab_id)}/"


# --- Building a lab lane

def lab_adapters(lab_id: str, parts: frozenset[str]):
    """The product's own adapters on the lab's topics; with no parts, all in memory."""
    return real_adapters(parts, topic_prefix=topic_prefix(lab_id)) if parts else make_memory_adapters


def connect_shop(lane, address: str) -> None:
    """The lab's shop as the tenant's live orders database, read-only, as a person would connect it."""
    schema = lane.seed["tenant_id"]
    connection = Connection(connection_id=SHOP_CONNECTION, name="Lab shop", purpose="orders", kind="database", status="live",
                            database=DatabaseSpec(engine="postgres", schemas=[schema]), orders_map=lab_shop.order_map(schema), created_by="research_lab")
    conn_call.save(lane, conn_call.set_secret(lane, connection, "database_url", address))


@contextmanager
def one_build_at_a_time(on_postgres: bool):
    """Across every process: held on its own connection, released when the build ends or the process dies."""
    with BUILDING:
        if not on_postgres:
            yield
            return
        with psycopg.connect(store_postgres.DATABASE_URL, autocommit=True) as connection:
            connection.execute("SELECT pg_advisory_lock(%s)", (BUILD_LOCK,))
            yield


def create_lab(lab_id: str, seed: dict, model, now: datetime, shop: dict | None = None, parts: frozenset[str] = LAB_PARTS, new_id=None):
    """A lane for one lab tenant, seeded from the pack, with its tools in shadow mode. Building it again reuses what is there."""
    # Step 1: refuse a non-lab id, or a part that does not answer
    checked(lab_id)
    missing = missing_infra(parts)
    if missing:
        raise LabInfraMissing(", ".join(missing))

    # Step 2: the real pipeline on the lab's own tenant and topics, acting in shadow; one lab builds at a time
    with one_build_at_a_time("postgres" in parts):
        lane = orchestrate.build_lane({**seed, "tenant_id": lab_id}, model, None, now, lab_adapters(lab_id, parts), new_id=new_id)
        lane.tooling.update(mode="shadow", send_email=None)

        # Step 3: its shop, for S5's orders and S7's payments
        if shop is not None:
            connect_shop(lane, lab_shop.build_shop(lab_id, shop))
    return lane


def close_lab(lane) -> None:
    """Stop the lane's worker and Kafka consumers, so teardown can remove their groups."""
    orchestrate.close_lane(lane)
    for consumer in getattr(lane.bus, "consumers", {}).values():
        consumer.close()
    getattr(lane.bus, "consumers", {}).clear()


# --- Teardown: one function per store, counting or deleting

def postgres_rows(lab_id: str, apply: bool) -> int:
    """Every product table with a tenant_id, by key: the lab id is the first column of each table's key."""
    verb = "DELETE" if apply else "SELECT count(*)"
    with store_postgres.connect() as connection:
        tables = [row[0] for row in connection.execute("SELECT table_name FROM information_schema.columns WHERE column_name = 'tenant_id' AND table_schema = 'public'")]
        results = [connection.execute(f"{verb} FROM {table} WHERE tenant_id = %s", (lab_id,)) for table in tables]  # names from the catalog
        return sum(result.rowcount if apply else result.fetchone()[0] for result in results)


def s3_objects(lab_id: str, apply: bool) -> int:
    client = store_s3.connect()
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=store_s3.S3_BUCKET, Prefix=object_prefix(lab_id))
    keys = [item["Key"] for page in pages for item in page.get("Contents", [])]
    for start in range(0, len(keys), 1000) if apply else []:  # S3 deletes at most 1000 keys per call
        client.delete_objects(Bucket=store_s3.S3_BUCKET, Delete={"Objects": [{"Key": key} for key in keys[start:start + 1000]]})
    return len(keys)


def valkey_keys(lab_id: str, apply: bool) -> int:
    client = store_valkey.connect()
    keys = list(client.scan_iter(match=f"{lab_id}:*", count=1000))
    if apply and keys:
        client.delete(*keys)
    return len(keys)


def kafka_topics_and_groups(lab_id: str, apply: bool) -> int:
    admin = AdminClient({"bootstrap.servers": kafka_admin.DEFAULT_BOOTSTRAP})
    prefix = topic_prefix(lab_id)
    groups = [g.group_id for g in admin.list_consumer_groups().result(kafka_admin.ADMIN_TIMEOUT_SECONDS).valid if g.group_id.startswith(prefix)]
    topics = [name for name in admin.list_topics(timeout=kafka_admin.ADMIN_TIMEOUT_SECONDS).topics if name.startswith(prefix)]
    if apply and groups:
        for future in admin.delete_consumer_groups(groups).values():
            future.exception(kafka_admin.ADMIN_TIMEOUT_SECONDS)
    if apply and topics:
        kafka_admin.delete_prefixed_topics(prefix)
    return len(groups) + len(topics)


def shop_schema(lab_id: str, apply: bool) -> int:
    found = lab_shop.shop_left(lab_id)
    if apply and found:
        lab_shop.drop_shop(lab_id)
    return found


STORES = {"postgres": (store_postgres.database_is_up, postgres_rows), "s3": (store_s3.s3_is_up, s3_objects),
          "valkey": (store_valkey.valkey_is_up, valkey_keys), "kafka": (kafka_admin.broker_is_up, kafka_topics_and_groups),
          "shop": (store_postgres.database_is_up, shop_schema)}


def leftovers(lab_id: str) -> dict:
    """What the lab still holds in each store; None for a store that does not answer, so it cannot be checked."""
    checked(lab_id)
    return {name: count(lab_id, False) if is_up() else None for name, (is_up, count) in STORES.items()}


def teardown(lab_id: str) -> dict:
    """Remove the lab from every store, then count again. complete is True only when every store answered and holds nothing.
    Safe to run again: a crash halfway leaves a lab the next teardown finishes."""
    checked(lab_id)
    removed = {name: clear(lab_id, True) if is_up() else None for name, (is_up, clear) in STORES.items()}
    left = leftovers(lab_id)
    return {"lab_id": lab_id, "removed": removed, "left": left, "complete": all(n == 0 for n in left.values())}
