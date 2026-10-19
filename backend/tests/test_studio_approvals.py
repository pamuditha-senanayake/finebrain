# test_studio_approvals.py: Studio changes that need a person (step 9d). They wait as a change request on a branch with
# an S8 approval; the drafter never approves; C4 needs two leaders and a cooling period; an approval merges through S14
# and the pipeline then reads the new values; a node that moved on makes a conflict. Uses: tests/studio_helpers.py.
from datetime import timedelta

from app.api import studio_approvals
from tests.studio_helpers import FOUNDER, REFUND_WF, SECOND, STEWARD, THIRD, build, change, decide, get, node, op

# Config
LONGER_WINDOW = {"fields": {"param.days": 45, "statement": "Customers may request a refund within 45 days of the purchase date."}}


def routed(client, patch: dict, kind: str = "policy", target: str = "policy_refund", persona: str = FOUNDER) -> tuple[str, str]:
    result = op(client, "studioApply", {"input": change(kind, target, patch, workflow=REFUND_WF if kind != "tool" else None), "acknowledgeBreaking": True}, persona).json()
    assert result["status"] == "routed", result
    _, request = get(client, f"change-requests/{result['changeRequestId']}")
    return result["changeRequestId"], request["approvalId"]


def test_a_policy_change_waits_then_reaches_the_pipeline():
    client, lane = build()
    cr_id, approval_id = routed(client, LONGER_WINDOW)
    assert node(lane, "policy", "policy_refund")["window_days"] == 30  # nothing changes before approval
    _, approval = get(client, f"approvals/{approval_id}")
    assert (approval["subject"], approval["status"], approval["criticality"]) == ({"kind": "change_request", "id": cr_id}, "pending", 3)
    assert decide(client, lane, approval_id, FOUNDER).json() == {"error": "requester_cannot_decide"}
    assert decide(client, lane, approval_id, SECOND).status_code == 200
    assert node(lane, "policy", "policy_refund")["window_days"] == 45  # what S7 reads
    wording = [k for k in lane.graph.latest("knowledge") if (k.get("version_ref") or {}).get("id") == "policy_refund" and not k.get("valid_to")]
    assert [k["text"] for k in wording] == [LONGER_WINDOW["fields"]["statement"]]  # what S6 reads: the old wording is closed
    assert get(client, f"change-requests/{cr_id}")[1]["status"] == "merged"
    assert get(client, f"approvals/{approval_id}")[1]["status"] == "approved"
    assert next(b for b in get(client, "branches")[1] if b["name"] == f"studio/{cr_id}")["status"] == "merged"
    assert get(client, "studio/pending")[1][0]["status"] == "applied"


def test_pausing_a_workflow_stops_its_routing_rule():
    client, lane = build()
    _, approval_id = routed(client, {"status": "paused"}, kind="workflow", target=REFUND_WF)
    decide(client, lane, approval_id, SECOND)
    assert node(lane, "resolver_rule", "rr_refund_email")["paused"] is True
    assert node(lane, "resolver_rule", "rr_billing_question").get("paused") is None


def test_a_capability_grant_needs_two_leaders_and_cooling():
    client, lane = build()
    grant = {"fields": {"capabilities": ["kb.read", "refund.propose", "reply.draft"]}}
    cr_id, approval_id = routed(client, grant, kind="agent", target="agent_refund_worker", persona=STEWARD)
    decide(client, lane, approval_id, SECOND)
    assert get(client, f"change-requests/{cr_id}")[1]["status"] == "awaiting_approval"
    decide(client, lane, approval_id, THIRD)
    request = get(client, f"change-requests/{cr_id}")[1]
    assert request["status"] == "approved" and request["coolingUntil"]
    studio_approvals.sweep(lane)
    assert "reply.draft" not in node(lane, "agent", "agent_refund_worker")["capabilities"]  # still cooling
    lane.now += timedelta(hours=25)
    studio_approvals.sweep(lane)
    assert "reply.draft" in node(lane, "agent", "agent_refund_worker")["capabilities"]
    assert get(client, f"studio/workflows/{REFUND_WF}/health")[1]["fixes"] == []  # the real gap is closed


def test_a_rejected_change_leaves_main_alone():
    client, lane = build()
    cr_id, approval_id = routed(client, LONGER_WINDOW)
    decide(client, lane, approval_id, SECOND, "reject")
    assert node(lane, "policy", "policy_refund")["window_days"] == 30
    assert get(client, f"change-requests/{cr_id}")[1]["status"] == "rejected"


def test_a_change_drafted_against_an_old_version_is_a_conflict():
    client, lane = build()
    _, first = routed(client, LONGER_WINDOW)
    second_cr, second = routed(client, {"fields": {"param.days": 20, "statement": "Customers may request a refund within 20 days of the purchase date."}})
    decide(client, lane, first, SECOND)
    decide(client, lane, second, SECOND)
    assert get(client, f"change-requests/{second_cr}")[1]["status"] == "conflict"
    assert node(lane, "policy", "policy_refund")["window_days"] == 45


def test_versions_show_main_and_the_change_branches():
    client, _ = build()
    cr_id, _ = routed(client, LONGER_WINDOW)
    names = {b["name"]: b["status"] for b in get(client, "branches")[1]}
    assert names["main"] == "protected" and names[f"studio/{cr_id}"] == "open"
    request = get(client, f"change-requests/{cr_id}")[1]
    assert "Window in days: 30 days → 45 days" in request["plainDiff"] and request["toBranch"] == "main"
    assert get(client, "change-requests/cr_missing")[0] == 404
