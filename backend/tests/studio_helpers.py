# studio_helpers.py: a Finebase HQ API with extra people for Studio tests: two more L1 leaders (so a change can be
# approved by someone other than its drafter, and C4 can get two) and an L3 operator. Used by: tests/test_studio*.py.
import copy

from fastapi.testclient import TestClient

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import fakes, orchestrate
from tests.golden import NOW

# Config
BASE, HQ = load_hq()
TENANT = BASE["tenant_id"]
FOUNDER, SECOND, THIRD, STEWARD, OPERATOR = "h-pamuditha", "h-second", "h-third", "h-udayanga", "h-op"
REFUND_WF = "wf_act_refund_request"
EXTRA = {SECOND: {"tier": "L1", "roles": ["leader", "dri"], "delegate": None, "name": "Second Leader"},
         THIRD: {"tier": "L1", "roles": ["leader", "dri"], "delegate": None, "name": "Third Leader"},
         OPERATOR: {"tier": "L3", "roles": ["care-operator"], "delegate": None, "name": "Care Operator"}}


def build():
    seed = copy.deepcopy(BASE)
    seed["people"] = {**seed["people"], **EXTRA}
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    return TestClient(create_api_app(lane, HQ)), lane


def get(client, resource: str, persona: str = FOUNDER):
    response = client.get(f"/api/t/{TENANT}/{resource}", headers={"x-persona": persona})
    return response.status_code, response.json()


def op(client, name: str, body: dict, persona: str = FOUNDER):
    return client.post(f"/api/t/{TENANT}/ops/{name}", json=body, headers={"x-persona": persona})


def change(kind: str, target: str | None, patch: dict, intent: str = "update", workflow: str | None = REFUND_WF) -> dict:
    return {"intent": intent, "kind": kind, "targetId": target, "workflowId": workflow, "patch": patch}


def decide(client, lane, approval_id: str, persona: str, decision: str = "approve"):
    response = op(client, "decide", {"approvalId": approval_id, "decision": decision, "comment": ""}, persona)
    lane.bus.drain()
    return response


def node(lane, kind: str, node_id: str) -> dict:
    return next(n for n in lane.graph.latest(kind) if n["_ref"]["id"] == node_id)
