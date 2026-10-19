# test_forget.py: step 10, forgetting. Retire ends a document's valid time (an "as of" search still finds it); erase clears
# every layer and leaves only a tombstone. Review first, then the L1 confirms (twice for erase).
# Uses: app/pipeline/forget.py, app/api/forget_*.py, documents.py, routes.py, tests/test_documents.py (helpers).
import json
from datetime import timedelta

import pytest

from app.api import forget_layers
from app.pipeline import forget
from tests.golden import NOW
from tests.test_documents import FOUNDER, NOTE, TENANT, build, upload

# Config
STEWARD = "h-udayanga"
ASKED = "Saturday"  # a word only the uploaded note has
OTHER = b"Escalations\n\nWrite to help@finebase.lk when a customer waits more than a day. Reviewed every Saturday."


# --- Helpers

def filed(client, lane, name: str = "support_hours.md", data: bytes = NOTE) -> str:
    document_id = upload(client, name, data).json()["id"]
    lane.bus.drain()
    return document_id


def start(client, document_id: str, mode: str, persona: str = FOUNDER, reason: str = "out of date"):
    return client.post(f"/api/t/{TENANT}/documents/{document_id}/forget", json={"mode": mode, "reason": reason}, headers={"x-persona": persona})


def confirm(client, request_id: str, persona: str = FOUNDER):
    return client.post(f"/api/t/{TENANT}/forget/{request_id}/confirm", headers={"x-persona": persona})


def remove(client, document_id: str, mode: str) -> dict:
    """Walk the whole flow as the L1 and return the last answer."""
    answer = start(client, document_id, mode).json()
    while answer["confirmationsLeft"]:
        answer = confirm(client, answer["requestId"]).json()
    return answer


def library(client) -> list[dict]:
    return client.get(f"/api/t/{TENANT}/documents", headers={"x-persona": FOUNDER}).json()


def todays_hits(lane, word: str = ASKED) -> list[str]:
    return [hit["item_id"] for hit in lane.chunks.by_text(word, ["chunk"], lane.now, lane.now, 20)]


# --- The registry

def test_every_store_has_a_layer():
    assert forget.uncovered_stores() == []
    assert {layer.name for layer in forget.LAYERS} >= {"Search", "Graph", "Files", "Intake", "Conversations", "Vault", "Library", "Messages"}
    assert [layer.name for layer in forget.LAYERS if layer.final] == ["Library"]


# --- Retire

def test_retire_ends_the_valid_time_but_keeps_history():
    client, lane = build()
    document_id = filed(client, lane)
    assert todays_hits(lane)
    before = lane.now
    lane.now = lane.bus.now = NOW + timedelta(days=30)
    answer = remove(client, document_id, "retire")
    assert answer["status"] == "done" and answer["receipt"]["verified"] and answer["level"] == 3
    assert todays_hits(lane) == []  # today's search no longer finds it
    assert lane.chunks.by_text(ASKED, ["chunk"], before + timedelta(days=1), lane.now, 20)  # "as of last month" does
    assert not [n for n in lane.graph.latest("knowledge") if n["source"]["document_id"] == document_id]
    assert lane.graph.history("knowledge", f"{document_id}_c1")[0]["text"]  # the closed node still has its first version
    shown = library(client)[0]
    assert shown["extractionStatus"] == "retired" and [step["layer"] for step in shown["receipt"]["layers"]][0] == "Search"


def test_ask_stops_citing_a_retired_document():
    seen = []

    def answerer(question, documents, history=(), address="sir"):
        seen.extend(item_id for item_id, _ in documents)
        return "Until 6 pm.", [item_id for item_id, _ in documents if item_id.startswith("doc_")]

    client, lane = build(answerer)
    document_id = filed(client, lane)
    ask = lambda: client.post(f"/api/t/{TENANT}/ask", json={"question": "What are the support hours on Saturday?"}, headers={"x-persona": FOUNDER}).json()
    assert ask()["citations"]
    remove(client, document_id, "retire")
    seen.clear()
    assert ask()["citations"] == [] and not any(item.startswith("doc_") for item in seen)


def test_retired_document_is_not_filed_again_by_a_redelivery():
    client, lane = build()
    document_id = filed(client, lane)
    remove(client, document_id, "retire")
    signal = next(s for s in lane.signals.values() if s.dedup_key.endswith(document_id))
    from app.pipeline.stages_file import file_document
    file_document(lane, signal)
    assert todays_hits(lane) == [] and lane.records.load("document", document_id)["status"] == "retired"


# --- Erase

def test_erase_needs_two_confirmations_and_warns_between():
    client, lane = build()
    document_id = filed(client, lane)
    first = start(client, document_id, "erase").json()
    assert first["level"] == 4 and first["confirmationsLeft"] == 2 and "cannot be undone" in first["warning"]
    second = confirm(client, first["requestId"]).json()
    assert second["status"] == "review" and second["confirmationsLeft"] == 1 and "Last check" in second["warning"]
    assert todays_hits(lane) and lane.records.load("document", document_id)  # nothing is gone yet
    done = confirm(client, first["requestId"]).json()
    assert done["status"] == "done" and done["receipt"]["verified"] and done["confirmationsLeft"] == 0


def test_erase_clears_every_layer_and_leaves_a_tombstone():
    client, lane = build()
    document_id = filed(client, lane)
    assert lane.vault  # the note's email was masked into the vault
    remove(client, document_id, "erase")
    assert lane.chunks.of_document(document_id) == [] and todays_hits(lane) == []
    assert all("text" not in version for version in lane.graph.history("knowledge", f"{document_id}_c1"))
    assert not [uri for uri in lane.object_store if document_id in uri]
    assert not lane.vault and not lane.signals and not lane.seen_keys
    assert lane.records.load("document", document_id) is None
    assert lane.records.load("tombstone", document_id)["reason"] == "out of date"
    row = library(client)[0]
    assert (row["title"], row["extractionStatus"]) == ("Removed", "erased") and row["receipt"]["verified"]
    everything = json.dumps([list(lane.records.versions.values()), [e.payload for kept in lane.bus.topics.values() for e in kept], lane.audit.in_order(), list(lane.object_store.values())], default=str)
    assert ASKED not in everything and "help@finebase.lk" not in everything
    assert lane.audit.in_order()[-1]["topic"] == "forget.completed"


def test_erase_scrubs_the_conversation_that_cited_it():
    def answerer(question, documents, history=(), address="sir"):
        return "Until 6 pm on Saturday.", [item_id for item_id, _ in documents if item_id.startswith("doc_")]

    client, lane = build(answerer)
    document_id = filed(client, lane)
    body = client.post(f"/api/t/{TENANT}/ask", json={"question": "Support hours on Saturday?"}, headers={"x-persona": FOUNDER}).json()
    remove(client, document_id, "erase")
    turns = client.get(f"/api/t/{TENANT}/ask/turns?conversation={body['conversationId']}", headers={"x-persona": FOUNDER}).json()
    assert [turn["answer"] for turn in turns] == ["Source removed."] and turns[0]["question"]


def test_a_value_two_documents_share_stays_until_the_last_one_goes():
    client, lane = build()
    first, second = filed(client, lane), filed(client, lane, "escalations.md", OTHER)
    assert len(lane.vault) == 1  # the same email gives the same token
    remove(client, first, "erase")
    assert len(lane.vault) == 1
    remove(client, second, "erase")
    assert not lane.vault


def test_a_job_that_fails_its_check_can_run_again(monkeypatch):
    client, lane = build()
    document_id = filed(client, lane)
    monkeypatch.setattr(forget_layers.FilesLayer, "verify", lambda self, lane, item, mode: False)
    answer = remove(client, document_id, "erase")
    assert answer["status"] == "incomplete" and answer["receipt"]["failed"] == ["Files"]
    assert lane.records.load("document", document_id) and not lane.records.load("tombstone", document_id)  # the record waits for a clean check
    monkeypatch.undo()
    assert confirm(client, answer["requestId"]).json()["status"] == "done"
    assert lane.records.load("tombstone", document_id)


# --- Review and who may

def test_review_lists_what_depends_on_the_document():
    client, lane = build()
    document_id = filed(client, lane)
    lane.graph.put("policy", "pol_support", 1, "cmt_test", {"name": "Support rule", "text": f"Hours come from {document_id}_c1."})
    assert start(client, document_id, "retire").json()["dependents"] == [{"type": "policy", "id": "pol_support", "label": "Support rule"}]


def test_only_the_l1_may_remove_and_bad_requests_are_refused():
    client, lane = build()
    document_id = filed(client, lane)
    assert start(client, document_id, "erase", STEWARD).status_code == 403
    request_id = start(client, document_id, "erase").json()["requestId"]
    assert confirm(client, request_id, STEWARD).status_code == 403
    assert start(client, "doc_unknown", "erase").status_code == 404
    assert start(client, document_id, "shred").status_code == 400
    assert confirm(client, "fgt_unknown").status_code == 404
    done = remove(client, document_id, "retire")
    assert confirm(client, done["requestId"]).status_code == 409 and start(client, document_id, "retire").status_code == 409
    assert todays_hits(lane) == []
