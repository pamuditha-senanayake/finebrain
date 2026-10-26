# activity_world.py: the Landing page chat activity, built through Workflow Studio's own API the way a person builds it in
# the browser: a draft workflow, a sensor on the Landing chat connection, an owner agent, a policy, one skill, then live.
# A visitor's message comes in through the real S1 inbound path and the whole pipeline runs; the reply leaves through the
# connection's reply action. A stand-in portal answers in memory tests; test_activity_real.py uses the real one.
# Uses: api/hq.py, api/routes.py, conn_call.py, conn_inbound.py, orchestrate.py, samples/findbase_portal_manifest.json.
import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import conn_call, conn_inbound, fakes, orchestrate
from app.pipeline.conn_call import Connection
from app.pipeline.conn_spec import Manifest
from tests.golden import NOW

# Config
BASE, HQ = load_hq()
FOUNDER, LANDING, WF = "h-pamuditha", "conn_landing_chat", "wf_landing_page_chat"
MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "samples" / "findbase_portal_manifest.json").read_text())
STATEMENT = "The landing page chat never quotes prices, discounts or special terms. Demo and partnership requests go to a person."
STEPS = ["judgment: Answer from the product docs and the policy, citing them.", "tool: Reply to the visitor. [tool:reply_customer]",
         "tool: Hand demo, pricing and partnership requests to a person. [tool:escalate]"]


def build(make_adapters=None, tenant: str | None = None, key: str = "test-only-landing-key"):
    """Finebase HQ's API on a lane as HQ runs it (no stand-in gateway or sender), with the Landing chat connection live."""
    seed = {**copy.deepcopy(BASE), **({"tenant_id": tenant} if tenant else {})}
    options = {"make_adapters": make_adapters} if make_adapters else {}
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], None, NOW, **options)
    lane.tooling["send_email"] = None
    connection = Connection(connection_id=LANDING, name="Landing chat", purpose="website_chat", status="live", manifest=Manifest.model_validate(MANIFEST), created_by=FOUNDER)
    conn_call.save(lane, conn_call.set_secret(lane, connection, "api_key", key))
    return TestClient(create_api_app(lane, HQ)), lane


def apply(client, lane, kind: str, patch: dict, intent: str = "create", target: str | None = None, workflow: str | None = WF) -> str:
    """One confirmed Studio change, as the console sends it. Returns the changed item's id."""
    body = {"input": {"intent": intent, "kind": kind, "targetId": target, "workflowId": workflow, "patch": patch}, "acknowledgeBreaking": True}
    result = client.post(f"/api/t/{lane.seed['tenant_id']}/ops/studioApply", json=body, headers={"x-persona": FOUNDER}).json()
    assert result.get("status") == "applied", result
    lane.bus.drain()
    return result["targetId"]


def build_landing(client, lane, source: str = LANDING, live: bool = True) -> dict:
    """The whole activity, part by part, in the order of Studio's steps."""
    ids = {"workflow": apply(client, lane, "workflow", {"name": "Landing page chat", "description": "Questions from finebaselabs.com visitors"}, workflow=None)}
    ids["sensor"] = apply(client, lane, "sensor", {"name": "Landing chat feed", "fields": {"source": source, "sensorKind": "inbox", "events": ["message.created"]}})
    ids["agent"] = apply(client, lane, "agent", {"name": "Landing assistant", "fields": {"capabilities": ["kb.read", "reply.draft"], "autonomy": "supervised"}})
    ids["policy"] = apply(client, lane, "policy", {"name": "No price promises in chat", "fields": {"statement": STATEMENT}})
    ids["skill"] = apply(client, lane, "skill", {"name": "Answer landing visitors", "fields": {"agents": [ids["agent"]], "tools": ["tool:reply_customer", "tool:escalate"],
                                                                                            "policies": [ids["policy"]], "steps": STEPS}})
    if live:
        apply(client, lane, "workflow", {"status": "active"}, intent="update", target=WF)
    return ids


def visitor(lane, text: str, conversation: str = "c-landing-1") -> None:
    """A visitor's message as the site's feed hands it over, through the real S1 inbound path."""
    message = {"id": f"m-{uuid.uuid4()}", "conversation_id": conversation, "sender": "customer", "body": text, "created_at": "2026-10-10T04:30:00Z",
               "conversations": {"customer_id": "visitor-1"}}
    conn_inbound.take_in(lane, conn_call.load(lane, LANDING), [message])
    lane.bus.drain()


def stand_in_portal(monkeypatch) -> list[dict]:
    """The site's hub API in memory: it keeps what the brain posts and shows it back in the conversation."""
    posted: list[dict] = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append({**json.loads(request.content), "id": f"msg-{len(posted) + 1}", "at": datetime.now(timezone.utc).isoformat()})  # stamped as the real hub does
            return httpx.Response(201, json={"id": posted[-1]["id"]})
        return httpx.Response(200, json={"messages": [{"id": p["id"], "sender": "agent", "body": p["body"], "created_at": p["at"]} for p in posted]})

    monkeypatch.setattr(conn_call, "http", httpx.Client(transport=httpx.MockTransport(answer)))
    return posted


def node(lane, kind: str, node_id: str) -> dict | None:
    versions = lane.graph.history(kind, node_id)
    return versions[-1] if versions and not versions[-1].get("_closed") else None


def answer_with(policy_id: str, text: str = "Thanks for asking. A person from our team will reply about pricing.", waits: bool = False) -> dict:
    return {"tool": "reply_customer", "tool_input": {"message_plain": text, "awaits_customer": waits, "rationale_summary": "The policy says pricing goes to a person.",
                                                     "citations": [f"{policy_id}_statement"], "confidence": 0.9}}
