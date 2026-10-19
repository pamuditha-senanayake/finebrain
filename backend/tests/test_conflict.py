# test_conflict.py: step 14 slice 4, conflicts. A new price for a verified fact becomes a conflict; Propose lists what relied on
# the fact, asks Opus (or lets the newer source win) and opens a C3 change request; the leader's approval closes the old fact where
# the new one starts, so "as of" still finds the old price. Uses: fact_conflicts.py, stages_librarian.py, tests/test_librarian.py.
from datetime import datetime, timezone
from types import SimpleNamespace

from app.api import ask_memory
from tests.golden import NOW
from tests.test_documents import FOUNDER, TENANT
from tests.test_extract import CONTRACT, FEE, answering, filed
from tests.test_librarian import accepted_lane, get, op

# Config
RAISED = {**FEE, "quote": "The monthly fee is LKR 45,000", "value_raw": "LKR 45,000", "value_normalized": "LKR 4500000", "valid_from": "2027-01-01"}
NEW_TERMS = CONTRACT.replace(b"40,000", b"45,000")


# --- Helpers

def conflicted(resolve=None):
    """A verified fee, then a second contract with a new fee. Returns the client, lane, old fact id and the conflict item."""
    client, lane, fact_id = accepted_lane(FEE)
    lane.extract, lane.resolve = answering(RAISED)[0], resolve
    filed(client, lane, "Lanka Print supplier agreement 2027.md", NEW_TERMS)
    item = next(i for i in get(client, "librarian") if i["kind"] == "conflict")
    return client, lane, fact_id, item


def opus(winner: str, valid_from: str | None = "2027-01-01"):
    """A Claude Opus stand-in that answers with this winner."""
    block = SimpleNamespace(type="tool_use", name="propose_resolution", input={"winner": winner, "valid_from": valid_from, "reason": "The 2027 agreement is newer."})
    return lambda system, messages, tools: SimpleNamespace(content=[block])


def on(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


# --- Proposing

def test_a_new_value_is_a_conflict_with_the_current_fact():
    _, _, fact_id, item = conflicted()
    assert item["status"] == "open" and item["factIds"] == [fact_id]


def test_propose_opens_a_c3_change_request_for_the_dri():
    client, lane, fact_id, item = conflicted()
    answer = op(client, "librarianPropose", item["id"]).json()
    request = next(cr for cr in get(client, "change-requests") if cr["id"] == answer["id"])
    assert (request["kind"], request["criticality"], request["status"], request["dri"]) == ("fact", 3, "awaiting_approval", FOUNDER)
    assert request["tests"]["passed"] == 3 and request["impactPreview"]["runsReplayed"] == 0  # the console needs both before it lets anyone approve
    shown = next(i for i in get(client, "librarian") if i["id"] == item["id"])
    assert shown["status"] == "proposed" and shown["proposal"]["winningSource"] == "Lanka Print supplier agreement 2027"
    assert shown["proposal"]["newValidFrom"].startswith("2027-01-01") and "newer source wins" in answer["reason"]
    assert answer["id"] not in {p["changeRequestId"] for p in get(client, "studio/pending")}  # Studio lists only its own changes


def test_what_relied_on_the_fact_is_listed():
    client, lane, fact_id, item = conflicted()
    ask_memory.remember(lane, "conv_1", FOUNDER, "What is the fee?", "LKR 40,000.", [fact_id])
    op(client, "librarianPropose", item["id"])
    shown = next(i for i in get(client, "librarian") if i["id"] == item["id"])
    assert shown["proposal"]["dependents"] == [{"type": "conversation", "id": "conv_1", "label": "An Ask answer"}]


def test_opus_may_keep_the_current_fact():
    client, lane, fact_id, item = conflicted(opus("current"))
    assert op(client, "librarianPropose", item["id"]).json() == {"id": None, "kept": True, "reason": "The 2027 agreement is newer."}
    assert next(i for i in get(client, "librarian") if i["id"] == item["id"])["status"] == "resolved" and not get(client, "change-requests")


def test_a_model_outage_falls_back_to_the_newer_source():
    def down(system, messages, tools):
        raise ConnectionError("model down")
    client, _, _, item = conflicted(down)
    assert "did not answer" in op(client, "librarianPropose", item["id"]).json()["reason"]


# --- Approving

def test_approval_closes_the_old_fact_where_the_new_one_starts():
    client, lane, fact_id, item = conflicted(opus("new"))
    answer = op(client, "librarianPropose", item["id"]).json()
    approval_id = next(cr for cr in get(client, "change-requests") if cr["id"] == answer["id"])["approvalId"]
    assert client.post(f"/api/t/{TENANT}/ops/decide", json={"approvalId": approval_id, "decision": "approve"}, headers={"x-persona": FOUNDER}).json() == {"ok": True}
    lane.bus.drain()
    old = lane.graph.latest("fact")
    assert {f["item_id"]: f["status"] for f in old}[fact_id] == "superseded" and len(old) == 2
    assert next(i for i in get(client, "librarian") if i["id"] == item["id"])["status"] == "resolved"
    before, after = ([c for c in lane.chunks.by_text("monthly fee", ["fact"], on(day), on(day), 5) if c["item_id"].startswith("fact_")] for day in ("2026-12-01", "2027-02-01"))
    assert [c["value"]["raw"] for c in before] == ["LKR 40,000"] and [c["value"]["raw"] for c in after] == ["LKR 45,000"]


def test_accepting_one_claim_turns_a_waiting_rival_into_a_conflict():
    client, lane = accepted_lane(FEE)[:2]
    lane.extract = answering(RAISED)[0]
    filed(client, lane, "Lanka Print supplier agreement 2027.md", NEW_TERMS)
    assert {i["kind"] for i in get(client, "librarian") if i["status"] == "open"} == {"conflict"}
    assert NOW < on("2027-01-01")  # the new fee is still in the future on the test clock
