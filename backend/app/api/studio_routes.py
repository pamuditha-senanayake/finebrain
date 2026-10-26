# studio_routes.py: Workflow Studio and Versions on the Finebase HQ API. Reads go through resource(); writes are the
# review (a read: nothing changes), studioApply and studioSuggest. Studio's consumer of approvals.decided merges
# approved change requests. The assistant (studio/chat, step 9e) only drafts, through the same review. Used by: routes.py. Uses: studio_*.py, versions_views.py.
from fastapi import FastAPI, Header, HTTPException, Request

from app.api import studio_approvals, studio_options, studio_views, versions_views
from app.api.studio_apply import apply_op, suggest_op
from app.api.studio_chat import chat
from app.api.studio_draft import StudioError
from app.api.studio_review import review
from app.pipeline import stages_version


def resource(lane, resource: str, query: dict):
    """The Studio and Versions resources, or None when the resource is not one of them."""
    parts = resource.split("/")
    if resource == "studio/workflows":
        return studio_views.summaries(lane)
    if parts[:2] == ["studio", "workflows"] and len(parts) == 3:
        return studio_views.detail(lane, parts[2]) or not_found()
    if parts[:2] == ["studio", "workflows"] and len(parts) == 4 and parts[3] == "health":
        return studio_views.health_view(lane, parts[2]) or not_found()
    simple = {"studio/tools": studio_views.tools_view, "studio/pending": studio_views.pending_view, "notifications": studio_views.notifications_view,
              "studio/options": studio_options.options,
              "branches": versions_views.branches_view}
    if resource in simple:
        return simple[resource](lane)
    if resource == "studio/revisions":
        return studio_views.revisions_view(lane, query)
    if resource == "commits":
        return versions_views.commits_view(lane, query)
    if parts[0] == "change-requests":
        return versions_views.change_requests_view(lane, parts[1] if len(parts) > 1 else None) or ([] if len(parts) == 1 else not_found())
    return None


def not_found():
    raise LookupError("not_found")


def register(app: FastAPI, lane, check, chatter=None) -> None:
    """Add Studio's POST routes. Must come before the general ops route, so these win."""
    lane.bus.subscribe("approvals.decided", "studio", "S14", lambda envelope: studio_approvals.on_decision(lane, envelope))
    stages_version.ensure_main(lane)  # main shows as the protected branch from the first day

    async def run(tenant: str, request: Request, persona: str, action):
        check(tenant, persona)
        try:
            return action(await request.json())
        except StudioError as error:
            raise HTTPException(error.status, str(error)) from None

    @app.post("/api/t/{tenant}/studio/review")
    async def studio_review(tenant: str, request: Request, x_persona: str = Header(default="")):
        """The review card for a change: a chat reply that carries the proposal. Body: {input, workflowId}."""
        return await run(tenant, request, x_persona, lambda body: {"answer": "", "bullets": [], "cards": [], "suggestions": [], "focus": None, "workflowId": None,
                                                                   "story": None, "proposal": review(lane, x_persona, body["input"])})

    @app.post("/api/t/{tenant}/studio/chat")
    async def studio_chat(tenant: str, request: Request, x_persona: str = Header(default="")):
        """The assistant: Claude drafts, the person confirms. Body: ChatRequest."""
        return await run(tenant, request, x_persona, lambda body: chat(lane, chatter, x_persona, body))

    @app.post("/api/t/{tenant}/ops/studioApply")
    async def studio_apply(tenant: str, request: Request, x_persona: str = Header(default="")):
        return await run(tenant, request, x_persona, lambda body: apply_op(lane, x_persona, body))

    @app.post("/api/t/{tenant}/ops/studioSuggest")
    async def studio_suggest(tenant: str, request: Request, x_persona: str = Header(default="")):
        return await run(tenant, request, x_persona, lambda body: suggest_op(lane, x_persona, body))
