# test_studio.py: Workflow Studio on the Finebase HQ API (step 9d): the workflows built from the running graph, their
# health, the server review, low risk changes applied at once through S14, and Studio edits reaching what the
# pipeline reads, and the repair of a store written before Studio. Approvals are in test_studio_approvals.py.
# Uses: tests/studio_helpers.py, scripts/repair_studio_views.py.
from app.pipeline.store_graph import MemoryGraph, load_seed
from scripts.repair_studio_views import repair
from tests.studio_helpers import BASE, FOUNDER, OPERATOR, REFUND_WF, STEWARD, TENANT, build, change, get, node, op


# --- Reading

def test_workflows_come_from_the_running_graph():
    client, _ = build()
    _, flows = get(client, "studio/workflows")
    refund = next(f for f in flows if f["id"] == REFUND_WF)
    assert (refund["name"], refund["counts"]["skill"], refund["counts"]["tool"], refund["counts"]["sensor"]) == ("Refund handling", 1, 3, 2)
    assert refund["health"]["breaks"] == 1  # the refund worker lacks reply.draft, which S7 would deny
    _, detail = get(client, f"studio/workflows/{REFUND_WF}")
    assert {i["id"] for i in detail["items"]} >= {"skill_refund_handling", "agent_refund_worker", "policy_refund", "tool:issue_refund"}
    _, health = get(client, f"studio/workflows/{REFUND_WF}/health")
    assert health["fixes"][0]["label"] == "Grant reply.draft to Refund worker"
    assert get(client, "studio/workflows/wf_nothing")[0] == 404


def test_review_is_rebuilt_on_the_server():
    client, _ = build()
    body = {"input": change("policy", "policy_refund", {"fields": {"param.days": 45}}), "workflowId": REFUND_WF}
    proposal = client.post(f"/api/t/{TENANT}/studio/review", json=body, headers={"x-persona": FOUNDER}).json()["proposal"]
    assert proposal["changes"] == [{"field": "param.days", "label": "Window in days", "before": "30 days", "after": "45 days"}]
    assert (proposal["review"]["criticality"], proposal["review"]["authority"]["route"]) == (3, "apply")  # an L1 approves their own change
    drafted = client.post(f"/api/t/{TENANT}/studio/review", json=body, headers={"x-persona": STEWARD}).json()["proposal"]
    assert drafted["review"]["authority"]["route"] == "approval"  # an L2 steward sends it for approval


# --- Applying at once

def test_a_wording_change_applies_through_s14():
    client, lane = build()
    result = op(client, "studioApply", {"input": change("workflow", REFUND_WF, {"description": "Refunds from email and chat"}, workflow=REFUND_WF)}).json()
    assert result["status"] == "applied" and result["revisionId"]
    lane.bus.drain()
    assert node(lane, "workflow", REFUND_WF)["studio"]["description"] == "Refunds from email and chat"
    _, revisions = get(client, f"studio/revisions?target={REFUND_WF}")
    assert revisions[0]["summary"] == "Description: Refunds from email and chat"
    _, commits = get(client, "commits?branch=main")
    assert commits[0]["message"].startswith("Update workflow")


def test_a_skill_edit_reaches_what_s6_reads():
    client, lane = build()
    steps = node(lane, "skill", "skill_refund_handling")["studio"]["fields"]["steps"]
    new_steps = [*steps[:-1], "tool: If the payment cannot be found, escalate to a person. [tool:escalate]"]
    result = op(client, "studioApply", {"input": change("skill", "skill_refund_handling", {"fields": {"steps": new_steps}}), "acknowledgeBreaking": True}).json()
    assert result["status"] == "applied"  # C3, applied on the L1's own approval
    lane.bus.drain()
    skill = node(lane, "skill", "skill_refund_handling")
    assert skill["steps"][-1] == "If the payment cannot be found, escalate to a person."  # what S6 reads


def test_a_new_template_is_added_to_its_workflow():
    client, lane = build()
    result = op(client, "studioApply", {"input": change("template", None, {"name": "Refund log", "fields": {"cadence": "weekly"}}, intent="create")}).json()
    assert result["status"] == "applied"
    flow = node(lane, "workflow", REFUND_WF)["studio"]
    assert result["targetId"] in flow["members"]


# --- Who may change what

def test_l3_cannot_apply_but_can_suggest():
    client, lane = build()
    wording = change("workflow", REFUND_WF, {"description": "Faster refunds"}, workflow=REFUND_WF)
    assert op(client, "studioApply", {"input": wording}, OPERATOR).status_code == 403
    assert op(client, "studioSuggest", {"input": wording, "note": "please"}, OPERATOR).json()["status"] == "suggested"
    _, notices = get(client, "notifications")
    assert notices[0]["to"] == FOUNDER and "suggests" in notices[0]["body"]


def test_a_steward_drafts_and_never_applies():
    client, _ = build()
    result = op(client, "studioApply", {"input": change("workflow", REFUND_WF, {"description": "Steward wording"}, workflow=REFUND_WF)}, STEWARD).json()
    assert result["status"] == "routed"


def test_an_l1_applies_their_own_c3_and_c4_changes_at_once():
    client, lane = build()
    policy = change("policy", "policy_refund", {"fields": {"param.days": 45, "statement": "Customers may request a refund within 45 days of the purchase date."}})
    assert op(client, "studioApply", {"input": policy, "acknowledgeBreaking": True}).json()["status"] == "applied"  # C3
    grant = change("agent", "agent_refund_worker", {"fields": {"capabilities": ["kb.read", "refund.propose", "reply.draft"]}})
    assert op(client, "studioApply", {"input": grant, "acknowledgeBreaking": True}).json()["status"] == "applied"  # C4
    lane.bus.drain()
    assert node(lane, "policy", "policy_refund")["window_days"] == 45 and "reply.draft" in node(lane, "agent", "agent_refund_worker")["capabilities"]


def test_breaking_needs_to_be_acknowledged():
    client, _ = build()
    no_agent = change("skill", "skill_refund_handling", {"fields": {"agents": []}})
    assert op(client, "studioApply", {"input": no_agent}).status_code == 409
    assert op(client, "studioApply", {"input": no_agent, "acknowledgeBreaking": True}, STEWARD).json()["status"] == "routed"


def test_nothing_to_change_is_refused():
    client, _ = build()
    assert op(client, "studioApply", {"input": change("workflow", REFUND_WF, {"name": "Refund handling"}, workflow=REFUND_WF)}).status_code == 422


# --- Repairing a store written before Studio

def test_the_repair_gives_old_nodes_their_view_once():
    client, lane = build()
    without_views = {**BASE, "skills": [strip(s) for s in BASE["skills"]], "agents": {k: strip(a) for k, a in BASE["agents"].items()},
                     "refund_policy": strip(BASE["refund_policy"])}
    lane.graph = MemoryGraph(TENANT)
    load_seed(lane.graph, without_views)
    review = lambda: client.post(f"/api/t/{TENANT}/studio/review", json={"input": change("policy", "policy_refund", {"fields": {"param.days": 45}})}, headers={"x-persona": FOUNDER})  # noqa: E731
    assert review().status_code == 404
    done = repair(lane, BASE)
    assert "policy_refund v4" in done["repaired"] and len(done["repaired"]) == 5 and not done["skipped"]
    assert node(lane, "policy", "policy_refund")["window_days"] == 30
    assert review().status_code == 200
    assert repair(lane, BASE)["commit"] is None


def strip(body: dict) -> dict:
    return {key: value for key, value in body.items() if key != "studio"}
