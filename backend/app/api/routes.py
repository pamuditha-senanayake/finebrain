# routes.py: the console API for Finebase HQ: GET /api/t/{tenant}/{resource}, POST ops/decide, the live stream, and
# capture. Screens not built yet answer [] (lists) or 501 (single objects); they never fall back to demo data.
# Used by: hq.py, tests/test_api.py. Uses: ask.py, connect_routes.py, documents.py, graph_map.py, studio_routes.py, vault_routes.py, ready_routes.py, learn_routes.py, memory_routes.py, versions_views.py, lists.py, views.py, capture_api.py, ui_stream.py, orchestrate.py.
import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.api import ask as asking
from app.api import ask_memory, connect_routes, conversations, documents, event_log_routes, forget_routes, grant_views, grants, learn_routes, lists_query, memory_routes, ready_routes, search, studio_approvals, studio_routes, vault_routes, versions_views, views
from app.api.graph_map import graph_resource
from app.api.lists import clusters_view, list_view, live_event, refusal_for, sensors_view, tenant_view
from app.pipeline import capture_api, orchestrate
from app.pipeline.contracts_run import Decision
from app.pipeline.ui_stream import stream_events

# Config
# The deployed console's address goes in CONSOLE_ORIGINS (comma separated), for example https://brain.vercel.app
CONSOLE_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000", *filter(None, os.environ.get("CONSOLE_ORIGINS", "").replace(" ", "").split(","))]
NOT_BUILT_OBJECTS = {"analytics"}  # single objects whose screens come later
NULLABLE_OBJECTS = {"digest"}


# --- The app

def create_api_app(lane, hq: dict, answerer=None, chatter=None) -> FastAPI:
    app = FastAPI(title="finebrain API")
    app.add_middleware(CORSMiddleware, allow_origins=CONSOLE_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    capture_api.register(app, lane)
    tenant_id = lane.seed["tenant_id"]
    started = lane.now  # sensors count events per hour since the API started

    def check(tenant: str, persona: str | None) -> None:
        if tenant != tenant_id:
            raise HTTPException(404, "unknown_tenant")
        if persona is not None and persona not in lane.seed["people"]:
            raise HTTPException(401, "unknown_persona")

    connect_routes.register(app, lane, check, chatter, hq["tenant"]["name"])  # before the general GET, so connections and their brief win
    @app.exception_handler(HTTPException)
    async def as_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse({"error": error.detail}, status_code=error.status_code)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "tenant": tenant_id}

    @app.get("/api/tenants")
    def tenants() -> list[dict]:
        return [{"id": tenant_id, "name": hq["tenant"]["name"], "isScaleDemo": False}]

    @app.get("/api/t/{tenant}/stream")
    def stream(tenant: str, limit: int | None = None) -> StreamingResponse:
        check(tenant, None)  # EventSource cannot send headers; sign-in will guard this in production
        return StreamingResponse(stream_events(lane.broadcaster, tenant, limit, lambda event: live_event(lane, event), named=False), media_type="text/event-stream")

    @app.get("/api/t/{tenant}/{resource:path}")
    def resource(tenant: str, resource: str, request: Request, x_persona: str = Header(default="")):
        check(tenant, x_persona)
        if resource == "tenant":
            return tenant_view(lane, hq)
        if resource == "clusters":
            return clusters_view(lane, hq)
        if resource in ("ask/turns", "ask/conversations"):
            try:
                return ask_memory.serve(lane, resource, request.query_params, x_persona)
            except ask_memory.NotYourConversation:
                raise HTTPException(403, "not_your_conversation") from None
        if resource == "conversations":
            return conversations.list_view(lane)
        if resource.startswith("conversations/"):
            return conversations.view(lane, resource.split("/", 1)[1]) or not_found_http()
        if resource == "documents":
            return documents.documents_view(lane)
        if resource == "search":
            return search.search(lane, x_persona, request.query_params.get("q", ""))
        if resource.startswith("lists/"):
            served = lists_query.page(lane, resource.removeprefix("lists/"), dict(request.query_params))
            if served is None:
                raise HTTPException(404, "not_found")
            return served
        if resource.startswith("documents/") and resource.endswith("/chunks"):
            return documents.chunks_view(lane, resource.split("/")[1])
        if resource == "sensors":
            return sensors_view(lane, hq, started)
        if resource == "humans":
            return [views.human_view(lane, pid, person).ui() for pid, person in lane.seed["people"].items()]
        try:
            graph = studio_routes.resource(lane, resource, dict(request.query_params))
            graph = graph if graph is not None else graph_resource(lane, hq, resource, dict(request.query_params))
        except LookupError:
            raise HTTPException(404, "not_found") from None
        if graph is not None:
            return graph
        served = list_view(lane, resource, dict(request.query_params))
        if served is not None:
            return served
        return detail_or_fallback(resource)

    def detail_or_fallback(resource: str):
        if resource in NOT_BUILT_OBJECTS:
            raise HTTPException(501, "not_connected_yet")
        kind, _, item_id = resource.partition("/")
        if kind == "runs" and item_id and (run := lane.records.load("run", item_id)):
            return views.run_detail(lane, run).ui()
        if kind == "approvals" and item_id and (approval := lane.records.load("approval", item_id)):
            return versions_views.approval_of(lane, approval)
        if item_id:
            raise HTTPException(404, "not_found")
        return None if resource in NULLABLE_OBJECTS else []

    studio_routes.register(app, lane, check, chatter)  # before the general ops route, so studioApply and studioSuggest win
    for module in (vault_routes, ready_routes, grant_views, documents, forget_routes, memory_routes, event_log_routes):  # the librarian, Check now, grants, uploads, forgetting, values, event logs
        module.register(app, lane, check)
    learn_routes.register(app, lane, check, chatter)  # counts, trends, Mark as wrong, Draft a fix (step 15)

    @app.post("/api/t/{tenant}/ops/{op}")
    async def operation(tenant: str, op: str, request: Request, x_persona: str = Header(default="")):
        check(tenant, x_persona)
        if op in conversations.OPS:  # L3 Conversations: take over, send, hand back, close
            try:
                return conversations.run_op(lane, op, await request.json(), x_persona)
            except conversations.NotPossible as why:
                raise HTTPException(why.status, why.reason) from None
        if op != "decide":
            raise HTTPException(501, "not_connected_yet")
        body = await request.json()
        decision = Decision(approval_id=body["approvalId"], decision=body["decision"], decided_by=[x_persona], decided_at=lane.now,
                            comment=body.get("comment") or "", delegated_to=body.get("delegateTo"))
        approval = lane.records.load("approval", decision.approval_id)
        kind = approval["subject"]["kind"] if approval else None  # a Studio or librarian change, a data source grant (step 16), or a run's action
        refused = studio_approvals.refusal_for(lane, approval, decision) if kind == "change_request" else grants.refusal_for(lane, approval, decision) if kind == "grant" else refusal_for(lane, decision.approval_id, decision)
        if refused:
            raise HTTPException(*refused)
        orchestrate.decide(lane, decision)
        return {"ok": True}

    @app.post("/api/t/{tenant}/ask")
    async def ask(tenant: str, request: Request, x_persona: str = Header(default="")):
        check(tenant, x_persona)
        body = await request.json()
        question = str(body.get("question") or "").strip()
        if not question:
            raise HTTPException(400, "empty_question")
        try:
            page = body.get("page") or {}
            return asking.ask(lane, answerer, x_persona, question, page.get("scope"), body.get("conversationId"), page).ui()
        except asking.AskUnavailable:
            raise HTTPException(503, "knowledge_unavailable") from None
        except ask_memory.NotYourConversation:
            raise HTTPException(403, "not_your_conversation") from None

    @app.post("/api/t/{tenant}/{rest:path}")
    def not_built(tenant: str, rest: str, x_persona: str = Header(default="")):
        check(tenant, x_persona)
        raise HTTPException(501, "not_connected_yet")

    return app


def not_found_http():
    raise HTTPException(404, "not_found")
