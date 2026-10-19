# test_entities.py: step 13a, the entity registry. One entity per real thing, keyed without personal data, typed links,
# and forgetting an upload clears what it told the registry. Runs on memory, and on Postgres when it answers.
# Uses: app/pipeline/entity_match.py, store_entities.py, orchestrate.py, tests/test_forget.py and test_documents.py (helpers).
import uuid

import pytest

from app.pipeline import fakes, orchestrate, store_postgres
from app.pipeline.entity_match import document_source, entity_id_of
from app.pipeline.store_entities import MemoryEntities, PostgresEntities
from tests.golden import NOW, SEED, raw_sample
from tests.test_documents import build
from tests.test_forget import filed, remove

# Config
PAYMENT = "pay_FB_20261004_0192"  # the payment in sample s2
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")


# --- Helpers

def make_lane():
    return orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)


def send(lane, key: str, external_id: str) -> None:
    orchestrate.capture_signal(lane, {**raw_sample(key), "external_id": external_id})
    lane.bus.drain()


def of_type(lane, entity_type: str) -> list[dict]:
    return [entity for entity in lane.entities.all() if entity["type"] == entity_type]


# --- Matching at S2

def test_the_same_customer_twice_is_one_entity():
    lane = make_lane()
    send(lane, "s2", "mail_a")
    send(lane, "s2", "mail_b")
    customers = of_type(lane, "customer")
    assert len(customers) == 1 and len(of_type(lane, "payment")) == 1
    assert len(lane.entities.sources_of(customers[0]["entity_id"])) == 2


def test_a_redelivery_adds_nothing():
    lane = make_lane()
    send(lane, "s2", "mail_a")
    send(lane, "s2", "mail_a")
    assert len(lane.entities.sources_of(of_type(lane, "customer")[0]["entity_id"])) == 1


def test_the_registry_holds_no_personal_data():
    lane = make_lane()
    send(lane, "s2", "mail_a")
    keys = [entity["key"] for entity in lane.entities.all()]
    assert of_type(lane, "customer")[0]["key"].startswith("pii_tok_")
    assert not any("@" in key or "Nimal" in key for key in keys)


def test_signals_carry_their_entity_ids():
    lane = make_lane()
    send(lane, "s2", "mail_a")
    signal = lane.bus.topics["signals.normalized"][0].payload
    assert entity_id_of("payment", PAYMENT) in signal["entity_ids"]
    assert entity_id_of("customer", signal["actor"]["ref"]) in signal["entity_ids"]


def test_a_customer_is_linked_to_their_payment_only():
    lane = make_lane()
    send(lane, "s2", "mail_a")
    send(lane, "s3", "mail_b")
    customers, payments = of_type(lane, "customer"), of_type(lane, "payment")
    assert len(customers) == 2 and len(payments) == 2
    links = lane.entities.links_of(entity_id_of("payment", PAYMENT))
    assert [link["rel"] for link in links] == ["paid_with"]
    assert len({link["from_id"] for link in links}) == 1


def test_the_company_is_known_before_any_signal():
    lane = make_lane()
    assert lane.entities.get(entity_id_of("organization", SEED["tenant_id"])) is not None


# --- Uploads and forgetting

def test_an_upload_mentions_its_payment_and_erasing_clears_it():
    client, lane = build()
    send(lane, "s2", "mail_a")  # the email also names the payment
    document_id = filed(client, lane, "refund_note.md", f"Refund note\n\nPayment {PAYMENT} was refunded in full.".encode())
    document = entity_id_of("document", document_id)
    assert {"mentions", "paid_with"} == {link["rel"] for link in lane.entities.links_of(entity_id_of("payment", PAYMENT))}

    answer = remove(client, document_id, "erase")
    assert next(layer for layer in answer["receipt"]["layers"] if layer["layer"] == "Entities")["result"] == "cleared"
    assert lane.entities.get(document) is None and not lane.entities.of_source(document_source(SEED["tenant_id"], document_id))
    assert lane.entities.get(entity_id_of("payment", PAYMENT)) is not None  # the email still mentions it
    assert [link["rel"] for link in lane.entities.links_of(entity_id_of("payment", PAYMENT))] == ["paid_with"]


def test_retiring_an_upload_keeps_its_entities():
    client, lane = build()
    document_id = filed(client, lane)
    remove(client, document_id, "retire")
    assert lane.entities.get(entity_id_of("document", document_id)) is not None


# --- The store, on memory and on Postgres

def exercise(store) -> None:
    """The same story on any store: two sources mention a payment, one goes, then the other."""
    payment, customer = entity_id_of("payment", "p1"), entity_id_of("customer", "t1")
    store.note(payment, "payment", "p1", "src_a", NOW)
    store.note(customer, "customer", "t1", "src_a", NOW)
    store.link(customer, "paid_with", payment, "src_a", NOW)
    store.note(payment, "payment", "p1", "src_b", NOW)
    assert store.sources_of(payment) == ["src_a", "src_b"] and len(store.links_of(payment)) == 1
    assert store.drop_source("src_a") == 4  # two mentions, one link, one orphan (the customer)
    assert store.get(customer) is None and store.get(payment) is not None and store.links_of(payment) == []
    store.drop_source("src_b")
    assert store.all() == []


def test_memory_store_forgets_by_source():
    exercise(MemoryEntities())


@NEEDS_POSTGRES
def test_postgres_store_forgets_by_source():
    tenant = f"test_entities_{uuid.uuid4().hex[:8]}"
    exercise(PostgresEntities(store_postgres.connect(), tenant))
