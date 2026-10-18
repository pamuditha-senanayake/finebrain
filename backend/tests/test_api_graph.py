# test_api_graph.py: the 9c read-only screens on the Finebase HQ API: agents, skills, policies, resolver rules and the
# knowledge graph, served from the graph S3, S5 and S7 read, with live numbers from runs. Memory pipeline, recorded Claude.
# Uses: app/api/routes.py, graph_views.py, graph_map.py, hq.py (load_hq), capture_api.py, orchestrate.py, tests/golden.py.
import pytest
from fastapi.testclient import TestClient

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import capture_api, fakes, orchestrate
from tests.golden import NOW, RAW, recorded_answers

# Config
SEED, HQ = load_hq()
TENANT = SEED["tenant_id"]
FOUNDER = "h-pamuditha"


# --- Helpers

@pytest.fixture
def client():
    """The HQ API after the s2 email, which the refund worker resolved on its own."""
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    api = TestClient(create_api_app(lane, HQ))
    body = RAW["s2_refund_monthly_in_policy"]["raw_body"].encode()
    headers = {"content-type": "message/rfc822", "x-external-id": RAW["s2_refund_monthly_in_policy"]["external_id"],
               "x-signature": capture_api.sign(SEED["connectors"]["conn_gmail_support"]["secret"], body)}
    assert api.post("/capture/conn_gmail_support", content=body, headers=headers).status_code == 202
    lane.bus.drain()
    return api


def get(client, resource: str):
    response = client.get(f"/api/t/{TENANT}/{resource}", headers={"x-persona": FOUNDER})
    return response.status_code, response.json()


# --- Agents

def test_agents_carry_names_skills_and_live_numbers(client):
    _, agents = get(client, "agents")
    worker = next(a for a in agents if a["id"] == "agent_refund_worker")
    assert (worker["name"], worker["tier"], worker["accessLevel"], worker["policies"]) == ("Refund worker", "L3", "confidential", ["policy_refund"])
    assert worker["skills"] == [{"id": "skill_refund_handling", "version": 3, "branch": "main"}]
    assert worker["taskSuccess"] == 1.0 and worker["errorRate"] == 0.0
    assert get(client, "agents/agent_refund_worker")[1]["id"] == "agent_refund_worker"
    assert get(client, "agents/agent_nobody") == (404, {"error": "not_found"})


# --- Skills and resolver

def test_skills_show_steps_trigger_and_policy(client):
    _, skills = get(client, "skills")
    refund = next(s for s in skills if s["id"] == "skill_refund_handling")
    assert [step["kind"] for step in refund["steps"]] == ["retrieval", "judgment", "tool", "tool"]
    assert refund["steps"][2]["tool"] == "issue_refund" and refund["policies"] == ["policy_refund"]
    assert refund["trigger"] == "Customer asks for money back on a payment" and refund["inputs"] == ["payment_ref"]
    assert refund["agentIds"] == ["agent_refund_worker"] and refund["health"]["taskSuccess"] == 1.0
    assert [s["version"] for s in get(client, "skills/skill_refund_handling")[1]] == [3]
    assert get(client, "skills?branch=sandbox") == (200, [])


def test_resolver_rules_pin_the_skill_version_and_count_runs(client):
    _, rules = get(client, "resolver")
    refund = next(r for r in rules if r["id"] == "rr_refund_email")
    assert refund["skill"] == {"id": "skill_refund_handling", "version": 3, "branch": "main"}
    assert refund["triggerEval"]["cases"] == 1 and "needs payment_ref" in refund["match"]


# --- Policies

def test_policy_versions_close_and_point_forward(client):
    _, versions = get(client, "policies/policy_refund")
    old, current = versions
    assert (old["version"], old["supersededBy"], old["freshness"]["intervalClosed"]) == (2, "policy_refund_v3", True)
    assert "14 days" in old["statement"] and old["validTo"] is not None
    assert current["supersededBy"] is None and current["validTo"] is None and "30 days" in current["statement"]
    assert current["rule"]["params"]["windowDays"] == 30 and current["criticality"] == 3
    assert current["dependents"] == [{"type": "skill", "id": "skill_refund_handling", "label": "Refund handling"}]
    assert get(client, "policies")[1] == versions


# --- Knowledge graph

def test_graph_links_agents_skills_tools_policies_and_documents(client):
    _, graph = get(client, "graph")
    ids = {node["id"] for node in graph["nodes"]}
    links = {(edge["source"], edge["target"], edge["kind"]) for edge in graph["edges"]}
    assert ("agent:agent_refund_worker", "skill:skill_refund_handling", "uses") in links
    assert ("skill:skill_refund_handling", "tool:issue_refund", "uses") in links
    assert ("policy:policy_refund", "skill:skill_refund_handling", "governs") in links
    assert any(kind == "evidences" and target == "policy:policy_refund" for _, target, kind in links)
    assert all(source in ids and target in ids for source, target, _ in links)
    facts = [node for node in graph["nodes"] if node["type"] == "fact"]
    assert facts and all(node["sensitivity"] == "confidential" for node in facts)


def test_studio_lists_are_empty_until_9d(client):
    assert get(client, "studio/workflows") == (200, [])
