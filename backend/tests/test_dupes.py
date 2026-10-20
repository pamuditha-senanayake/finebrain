# test_dupes.py: step 13d slice 5, duplicates and the core field dictionary. Chunks with the same words answer once (the
# best is kept, the others point to it and search skips them); forgetting the kept one lets the others answer again; every
# fact reads into who, what, when, amount and outcome. Runs on memory, and on Postgres when it answers.
# Uses: app/pipeline/stages_dupes.py, store_chunks_memory.py, store_chunks_tiers.py, field_dictionary.py, api/distiller.py, tests/test_forget.py.
import uuid

import pytest

from app.api import distiller
from app.pipeline import fakes, stages_dupes, store_postgres
from app.pipeline.field_dictionary import core_of
from app.pipeline.store_chunks import MemoryChunks
from app.pipeline.store_chunks_memory import fingerprint
from app.pipeline.store_chunks_pg import PostgresChunks
from tests.golden import NOW
from tests.test_documents import FOUNDER, TENANT, build
from tests.test_forget import filed, remove

# Config
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")
SAID = b"Our support desk answers within four working hours, Monday to Friday."
SAID_AGAIN = b"Our support desk answers within FOUR working hours -- Monday to Friday!"


def chunk(item_id: str, text: str, value: float = 1.0, **more) -> dict:
    return {"item_id": item_id, "kind": "chunk", "text": text, "value": value, "recorded_at": NOW.isoformat(), "valid_from": None, "valid_to": None, **more}


def filled(chunks):
    items = (chunk("a", "Policy: Refunds take five days.", 1.0, title="Policy"), chunk("b", "REFUNDS take five days!", 3.0), chunk("c", "Something else."),
             chunk("sum_day_x", "Refunds take five days."), chunk("d", "Refunds take five days.", 9.0, valid_to=NOW.isoformat()))
    for item in items:
        chunks.add(item, fakes.fake_embed([item["text"]])[0])
    chunks.set_values({item["item_id"]: item["value"] for item in items}, NOW)
    return chunks


def check_store(chunks) -> None:
    """The best of a group is kept; open chunks only; summaries never merge; reopening clears the mark."""
    assert chunks.duplicate_groups() == [["b", "a"]]
    chunks.mark_duplicates({"a": "b"})
    assert chunks.duplicates_of(["b"]) == ["a"] and chunks.duplicate_groups() == []
    assert {i["item_id"] for i in chunks.by_text("refunds five days", ["chunk"], NOW, NOW, 10)} == {"b", "sum_day_x"}  # "a" is skipped
    chunks.mark_duplicates({"a": None})
    assert "a" in [i["item_id"] for i in chunks.by_text("refunds five days", ["chunk"], NOW, NOW, 10)]


# --- Duplicates

def test_the_same_words_whatever_the_case_or_punctuation():
    assert fingerprint("Refunds take five days.") == fingerprint("  REFUNDS take five days!") != fingerprint("Refunds take six days.")


def test_memory_keeps_the_best_and_skips_the_rest():
    check_store(filled(MemoryChunks()))


@NEEDS_POSTGRES
def test_postgres_gives_the_same_answers():
    check_store(filled(PostgresChunks(store_postgres.connect(), f"test_dupes_{uuid.uuid4().hex[:8]}")))


def test_the_distiller_merges_and_forgetting_the_kept_one_lets_the_other_answer():
    client, lane = build()
    first, second = filed(client, lane, "desk_faq.md", SAID), filed(client, lane, "staff_handbook.md", SAID_AGAIN)  # two documents, not two versions
    ids = {doc: lane.chunks.of_document(doc)[0]["item_id"] for doc in (first, second)}
    assert distiller.distill(lane, None, "test")["merged"] == 1
    kept = next(doc for doc in (first, second) if not lane.chunks.full(ids[doc])[0].get("duplicate_of"))
    other = second if kept == first else first
    remove(client, kept, "erase")
    assert lane.chunks.full(ids[other])[0].get("duplicate_of") is None
    assert ids[other] in [i["item_id"] for i in lane.chunks.by_text("support desk working hours", ["chunk"], lane.now, lane.now, 10)]
    assert stages_dupes.merge(lane) == 0


# --- The core field dictionary

def test_every_fact_reads_into_the_same_five_fields():
    fee = {"predicate": "monthly_fee", "value": {"type": "money", "raw": "LKR 40,000", "normalized": "LKR 40000"}, "valid_from": "2026-10-01T00:00:00+00:00"}
    term = {"predicate": "term", "value": {"type": "date", "raw": "1 October 2026", "normalized": "2026-10-01"}}
    window = {"predicate": "refund_request_window", "value": {"type": "duration", "raw": "45 days", "normalized": "P45D"}, "valid_from": "2026-10-19"}
    assert core_of(fee, "lanka print") == {"core": {"who": "lanka print", "what": "monthly fee", "when": "2026-10-01", "amount": "LKR 40000", "outcome": None}, "extra": {}}
    assert core_of(term, "lanka print")["core"]["when"] == "2026-10-01"
    assert core_of(window, "refund policy") == {"core": {"who": "refund policy", "what": "refund request window", "when": "2026-10-19", "amount": None, "outcome": None},
                                                "extra": {"duration": "P45D"}}


def test_the_vault_shows_core_fields_for_every_fact():
    client, _ = build()
    facts = client.get(f"/api/t/{TENANT}/facts", headers={"x-persona": FOUNDER}).json()
    assert facts and all(set(f["core"]) == {"who", "what", "when", "amount", "outcome"} for f in facts)
