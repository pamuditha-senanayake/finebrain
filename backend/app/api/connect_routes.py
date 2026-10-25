# connect_routes.py: the console's connection desk. Talk to the guide (it drafts the connection), get the brief for the
# other side's coding agent, paste back that agent's whole answer, test it, switch it live or pause it; plus the signed
# push from their system. Used by: routes.py. Uses: connect_brief.py, connect_guide.py, conn_call.py, conn_test.py, conn_inbound.py.
import json

from fastapi import FastAPI, Header, HTTPException, Request

from app.api import connect_brief, connect_guide
from app.pipeline import conn_inbound, conn_test
from app.pipeline.conn_call import Connection, all_connections, load, remove, save, set_secret
from app.pipeline.conn_spec import KINDS, TEMPLATES, DatabaseSpec, label

# Config
MAY_MANAGE = {"L1", "L2"}
MAY_GO_LIVE = {"L1"}  # a live connection lets outside data in and lets agents act outside; the L1 decides


def view(connection: Connection) -> dict:
    """The connection as the console shows it. Secrets appear only as the names of those set."""
    return {
        "id": connection.connection_id, "name": connection.name, "system": connection.system, "goal": connection.goal,
        "platform": connection.platform or connection.system or connection.name, "kind": connection.kind, "later": connection.later,
        "tables": [table["table"] for table in connection.schema_summary],
        "status": connection.status, "needs": [{"name": n.name, "label": label(n.name), "text": n.text, "writes": n.writes, "required": n.required} for n in connection.needs],
        "baseUrl": connection.manifest.base_url if connection.manifest else None, "secretsSet": connection.secrets_set,
        "tests": connection.tests, "testedAt": connection.tested_at, "events": connection.events,
        "lastEventAt": connection.last_event_at, "lastError": connection.last_error,
    }


def audit(lane, connection: Connection, event: str, person: str) -> None:
    lane.audit.append(f"connection:{connection.connection_id}:{event}:{lane.now.isoformat()}", f"connection.{event}",
                      {"by": person, "at": lane.now.isoformat(), "reason": connection.name})


def take_answer(lane, connection: Connection, body: dict) -> Connection:
    """Their agent's whole answer (or the parts one by one): settings into the record, keys into the vault.
    Keys found are kept even when the settings have problems, so the person only fixes what is wrong."""
    manifest_text = body.get("manifest") if isinstance(body.get("manifest"), str) else json.dumps(body["manifest"]) if body.get("manifest") else None
    manifest, secrets, problems = connect_brief.read_answer(body.get("answer") or manifest_text) if (body.get("answer") or manifest_text) else (None, {}, [])
    secrets |= {name: str(body[name]).strip() for name in ("api_key", "webhook_secret") if str(body.get(name) or "").strip()}
    for name, value in secrets.items():
        connection = set_secret(lane, connection, name, value)
    if problems:
        save(lane, connection)
        raise HTTPException(422, {"problems": problems, "keysKept": sorted(secrets)})
    update = {"database": manifest} if isinstance(manifest, DatabaseSpec) else {"manifest": manifest} if manifest else {}
    status = "delivered" if (manifest or connection.manifest or connection.database) else "waiting"
    return save(lane, connection.model_copy(update=update | {"status": status, "tests": [], "tested_at": None}))


def register(app: FastAPI, lane, check, chatter=None, company: str = "Our company") -> None:
    """Every connection route. Before the catch-all routes."""

    def allowed(tenant: str, persona: str, tiers=MAY_MANAGE) -> None:
        check(tenant, persona)
        if lane.seed["people"][persona]["tier"] not in tiers:
            raise HTTPException(403, "not_allowed")

    def owned(tenant: str, persona: str, connection_id: str, tiers=MAY_MANAGE) -> Connection:
        allowed(tenant, persona, tiers)
        connection = load(lane, connection_id)
        if connection is None:
            raise HTTPException(404, "not_found")
        return connection

    @app.get("/api/t/{tenant}/connections")
    def listed(tenant: str, x_persona: str = Header(default="")) -> list[dict]:
        check(tenant, x_persona)
        return [view(connection) for connection in all_connections(lane)]

    @app.post("/api/t/{tenant}/connections")
    async def create(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        """Without the guide: a named connection that starts from a template (a website chat by default)."""
        allowed(tenant, x_persona)
        body = await request.json()
        name = str(body.get("name") or "").strip()[:80]
        if not name:
            raise HTTPException(400, "name_required")
        purpose = body.get("purpose") if body.get("purpose") in TEMPLATES else "website_chat"
        kind = body.get("kind") if body.get("kind") in KINDS else "api"
        connection = save(lane, Connection(connection_id=connect_guide.free_id(lane, name), name=name, system=name, purpose=purpose, kind=kind,
                                           platform=str(body.get("platform") or name)[:80], needs=TEMPLATES[purpose] if kind == "api" else [], created_by=x_persona))
        audit(lane, connection, "created", x_persona)
        return view(connection)

    @app.post("/api/t/{tenant}/connections/guide")
    async def guide_new(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        """The guide before a connection exists; it creates one when it drafts."""
        allowed(tenant, x_persona)
        body = await request.json()
        start = {"kind": body.get("kind") if body.get("kind") in KINDS else "other", "platform": str(body.get("platform") or "")[:80]}
        answer, connection = connect_guide.guide(chatter, lane, None, company, body.get("turns") or [], x_persona, start)
        source = load(lane, str(body.get("fromConnection") or "")) if connection else None
        if source is not None and body.get("fromItem") in source.later:  # started from "Next up": that line is done
            save(lane, source.model_copy(update={"later": [item for item in source.later if item != body["fromItem"]]}))
        return {"answer": answer, "connection": view(connection) if connection else None}

    @app.post("/api/t/{tenant}/connections/{connection_id}/guide")
    async def guide_one(tenant: str, connection_id: str, request: Request, x_persona: str = Header(default="")) -> dict:
        connection = owned(tenant, x_persona, connection_id)
        answer, connection = connect_guide.guide(chatter, lane, connection, company, (await request.json()).get("turns") or [], x_persona)
        return {"answer": answer, "connection": view(connection)}

    @app.get("/api/t/{tenant}/connections/{connection_id}/brief")
    def get_brief(tenant: str, connection_id: str, x_persona: str = Header(default="")) -> dict:
        return {"brief": connect_brief.brief(owned(tenant, x_persona, connection_id), company)}

    @app.post("/api/t/{tenant}/connections/{connection_id}/deliver")
    async def deliver(tenant: str, connection_id: str, request: Request, x_persona: str = Header(default="")) -> dict:
        connection = take_answer(lane, owned(tenant, x_persona, connection_id), await request.json())
        audit(lane, connection, "delivered", x_persona)
        return view(connection)

    @app.post("/api/t/{tenant}/connections/{connection_id}/test")
    def test(tenant: str, connection_id: str, x_persona: str = Header(default="")) -> dict:
        connection = owned(tenant, x_persona, connection_id)
        lines, keep = conn_test.run_test(lane, connection)
        status = connection.status if connection.status in ("live", "paused") else "tested" if conn_test.passed(lines) else connection.status
        return view(save(lane, connection.model_copy(update=keep | {"tests": lines, "tested_at": lane.now.isoformat(), "status": status})))

    @app.post("/api/t/{tenant}/connections/{connection_id}/live")
    async def switch(tenant: str, connection_id: str, request: Request, x_persona: str = Header(default="")) -> dict:
        connection = owned(tenant, x_persona, connection_id, MAY_GO_LIVE)
        turn_on = bool((await request.json()).get("on"))
        if turn_on and not conn_test.passed(connection.tests):
            raise HTTPException(409, "test_first")
        connection = save(lane, connection.model_copy(update={"status": "live" if turn_on else "paused"}))
        audit(lane, connection, "live" if turn_on else "paused", x_persona)
        return view(connection)

    @app.patch("/api/t/{tenant}/connections/{connection_id}")
    async def rename(tenant: str, connection_id: str, request: Request, x_persona: str = Header(default="")) -> dict:
        connection = owned(tenant, x_persona, connection_id)
        name = str((await request.json()).get("name") or "").strip()[:80]
        if not name:
            raise HTTPException(400, "name_required")
        connection = save(lane, connection.model_copy(update={"name": name}))
        audit(lane, connection, "renamed", x_persona)
        return view(connection)

    @app.delete("/api/t/{tenant}/connections/{connection_id}")
    def delete(tenant: str, connection_id: str, x_persona: str = Header(default="")) -> dict:
        connection = owned(tenant, x_persona, connection_id)
        audit(lane, connection, "deleted", x_persona)
        remove(lane, connection)
        return {"deleted": connection_id}

    @app.post("/capture/connections/{connection_id}/push", status_code=202)
    async def push(connection_id: str, request: Request) -> dict:
        connection = load(lane, connection_id)
        feed = connection.manifest.inbound if connection and connection.manifest else None
        header = (feed.push_signature_header if feed else None) or "x-signature"
        try:
            taken = conn_inbound.accept_push(lane, connection_id, await request.body(), request.headers.get(header, ""))
        except PermissionError as refused:
            raise HTTPException(401 if str(refused) == "signature" else 404, str(refused)) from None
        return {"taken": taken}
