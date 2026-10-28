# access_views.py: Security on the console. GET access-rules and access-tiers show the rules S7 really applies (the same ones as
# infra/opa/access.rego), and POST ops/accessCheck asks "would this be allowed?" without doing anything: the same rules, no run, no audit entry.
# Used by: lists.py, routes.py (register), tests. Uses: access.py, studio_model.py, contracts_reason.py.
from fastapi import FastAPI, Header, HTTPException, Request

from app.api import studio_model
from app.pipeline import access
from app.pipeline.contracts_reason import AccessCheck, Principal, Resource

# Config
GENERAL_RULES = [
    ("missing_capability", "Needs the capability", "every action", "public", "An agent acts only with a capability it holds. Handing work to a person is open to all."),
    ("sensitivity_by_tier", "Data by tier", "every read", "restricted", "Each tier reads up to a level. Restricted data stays with L1 and L2."),
    ("on_behalf_of", "Acting for a person", "work done for someone", "restricted", "An agent carries no more than the person it acts for may see."),
    ("opa_unreachable", "No answer, no", "every action", "public", "If the access service does not answer, the action is denied."),
]


def rules_view(lane) -> list[dict]:
    """The general rules, then one per tool that asks for a capability."""
    tenant = lane.seed["tenant_id"]
    general = [{"id": rule_id, "tenantId": tenant, "name": name, "appliesTo": applies, "requiresRoles": [], "requiresAttributes": {}, "requiresCapability": None,
                "sensitivity": sensitivity, "description": about} for rule_id, name, applies, sensitivity, about in GENERAL_RULES]
    tools = [i for i in studio_model.items(lane) if i["kind"] == "tool" and i["fields"].get("capability")]
    per_tool = [{"id": f"tool:{t['id']}", "tenantId": tenant, "name": t["name"], "appliesTo": f"tool:{t['id']}", "requiresRoles": [], "requiresAttributes": {},
                 "requiresCapability": t["fields"]["capability"], "sensitivity": t["fields"].get("sensitivity") or "internal",
                 "description": f"Only agents holding {t['fields']['capability']} may use this tool."} for t in tools]
    return general + per_tool


def tiers_view(lane) -> list[dict]:
    """Which data each tier reads, from most trusted to least."""
    order = ["public", "internal", "confidential", "restricted"]
    return [{"tier": tier, "reads": [s for s in order if s in access.READABLE[tier]]} for tier in ("L1", "L2", "L3")]


def homes_view(lane) -> dict:
    """Which workflow each part lives in, so Security can open a part in Studio."""
    return {i["id"]: i["workflowId"] for i in studio_model.items(lane) if i["workflowId"]}


def check_view(lane, body: dict) -> dict:
    """Run the access rules on a made-up action. Names the rule that decided, so a deny says why."""
    agent = next((a for a in lane.graph.latest("agent") if a["_ref"]["id"] == body.get("agentId")), None)
    if agent is None:
        raise LookupError("not_found")
    sensitivity, person = body.get("sensitivity"), body.get("onBehalfOf") or None
    if sensitivity not in access.ALL_SENSITIVITIES or not body.get("action"):
        raise ValueError("choose an action and how sensitive the data is")
    if person and person not in lane.seed["people"]:
        raise ValueError("unknown person")
    principal = Principal(type="agent", id=agent["_ref"]["id"], capabilities=list(agent.get("capabilities", [])), tier=agent["tier"])
    check = AccessCheck(check_id="preview", principal=principal, on_behalf_of=person, action=body["action"],
                        resource=Resource(type="preview", id="preview", cluster_id="", sensitivity=sensitivity))
    result = access.make_memory_checker(lane.seed["people"])(check)
    return {"allow": result["allow"], "ruleId": result["rule_id"], "reason": result["reason"], "tier": agent["tier"],
            "effectiveTier": access.effective_tier(agent["tier"], person, lane.seed["people"])}


def register(app: FastAPI, lane, check) -> None:
    @app.post("/api/t/{tenant}/ops/accessCheck")
    async def access_check(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        try:
            return check_view(lane, await request.json())
        except LookupError:
            raise HTTPException(404, "unknown_agent") from None
        except ValueError as reason:
            raise HTTPException(400, str(reason)) from None
