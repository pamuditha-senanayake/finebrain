# test_policy_follow_up.py: step 14, after a fact change merges. The refund window fact goes from 30 to 45 days; the refund
# policy still says 30, so the librarian drafts a Studio change for the policy's DRI; nothing changes until they approve.
# Uses: policy_follow_up.py, fact_conflicts.py, studio_approvals.py, tests/test_conflict.py, test_extract.py, test_librarian.py.
from app.api import policy_follow_up
from app.api.studio_changes import ChangeRecord
from tests.test_conflict import opus
from tests.test_documents import FOUNDER, TENANT
from tests.test_extract import answering, build, filed
from tests.test_librarian import STEWARD, get, op

# Config
POLICY_V1 = b"Sample refund policy\n\nCustomers may ask for a refund within 30 days."
WINDOW = {"quote": "Customers may ask for a refund within 30 days", "statement": "Customers may ask for a refund within 30 days.", "subject_type": "contract",
          "subject_name": "Sample refund policy", "predicate": "refund_request_window", "value_type": "duration", "value_raw": "30 days",
          "value_normalized": "P30D", "valid_from": None, "valid_to": None, "confidence": 0.95}
LONGER = {**WINDOW, "quote": "Customers may ask for a refund within 45 days", "statement": "Customers may ask for a refund within 45 days.",
          "value_raw": "45 days", "value_normalized": "P45D"}


# --- Helpers

def approve(client, lane, approval_id: str) -> None:
    client.post(f"/api/t/{TENANT}/ops/decide", json={"approvalId": approval_id, "decision": "approve"}, headers={"x-persona": FOUNDER})
    lane.bus.drain()


def window_changed():
    """The 30 day window verified, v2 says 45, and the fact change is approved. Returns the client, lane and the fact change request."""
    client, lane = build(answering(WINDOW)[0])
    filed(client, lane, "Sample refund policy v1.md", POLICY_V1)
    op(client, "librarianAccept", next(i for i in get(client, "librarian") if i["status"] == "open")["id"], STEWARD)
    lane.extract, lane.resolve = answering(LONGER)[0], opus("new", None)
    filed(client, lane, "Sample refund policy v2.md", POLICY_V1.replace(b"30", b"45"))
    cr_id = op(client, "librarianPropose", next(i for i in get(client, "librarian") if i["kind"] == "conflict")["id"]).json()["id"]
    approve(client, lane, next(cr for cr in get(client, "change-requests") if cr["id"] == cr_id)["approvalId"])
    return client, lane, ChangeRecord.model_validate(lane.records.load("change_request", cr_id))


def policy(lane) -> dict:
    return next(node for node in lane.graph.latest("policy") if node["_ref"]["id"] == "policy_refund")


# --- Finding what states the old value

def test_a_policy_may_write_the_value_another_way():
    assert policy_follow_up.rewritten("After the 30-day window, or within 30 days.", "30 days", "45 days") == "After the 45-day window, or within 45 days."
    assert policy_follow_up.rewritten("Up to LKR 50,000.", "LKR 50,000", "LKR 60,000") == "Up to LKR 60,000."


def test_a_policy_about_another_topic_is_left_alone():
    _, lane, record = window_changed()
    st = policy_follow_up.Studio.of(lane)
    assert policy_follow_up.stating(st, "payment_terms", "30 days") == [] and policy_follow_up.stating(st, "refund_request_window", "90 days") == []


# --- Drafting for the DRI

def test_a_merged_fact_change_drafts_the_policy_change_for_its_dri():
    client, lane, record = window_changed()
    assert record.status == "merged" and len(record.follow_ups) == 1
    drafted = ChangeRecord.model_validate(lane.records.load("change_request", record.follow_ups[0]))
    assert (drafted.kind, drafted.status, drafted.drafter, drafted.dri) == ("policy", "awaiting_approval", "librarian", FOUNDER)
    assert drafted.input["patch"]["fields"]["param.days"] == 45 and "45 day window" in drafted.input["patch"]["fields"]["statement"]
    assert "30 days to 45 days" in drafted.note and policy(lane)["window_days"] == 30  # nothing changes before the DRI approves
    assert any(n["to"] == FOUNDER and n["title"].startswith("Studio change") for n in lane.records.list_kind("notification"))


def test_the_dri_approval_makes_the_policy_say_45_days():
    client, lane, record = window_changed()
    approve(client, lane, ChangeRecord.model_validate(lane.records.load("change_request", record.follow_ups[0])).approval_id)
    assert policy(lane)["window_days"] == 45
    wording = [c["text"] for c in lane.chunks.by_text("refund window days", ["policy"], lane.now, lane.now, 10)]
    assert any("within 45 days" in text for text in wording) and not any("30" in text for text in wording)


def test_start_up_follows_up_a_fact_change_merged_before_once():
    _, lane, record = window_changed()
    lane.records.save("change_request", record.cr_id, record.model_copy(update={"follow_ups": None}))  # as if merged before this rule
    for drafted in record.follow_ups:  # and its drafted change never existed
        lane.records.save("change_request", drafted, ChangeRecord.model_validate(lane.records.load("change_request", drafted)).model_copy(update={"status": "rejected"}))
    assert policy_follow_up.follow_up_merged(lane) == 1 and policy_follow_up.follow_up_merged(lane) == 0
