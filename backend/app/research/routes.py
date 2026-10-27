# routes.py: the Research Lab API, its own app that main.py mounts at /research only when RESEARCH_LAB=enabled.
# Only the founder or a person with the research role may open it. It serves the lab's status and packs (pack_routes.py);
# later steps add preregistrations, experiments and results. Used by: app/main.py.
# Uses: research/store.py, research/pack_store.py, research/pack_routes.py, store_s3.py, api/routes.py (console origins).
import json
from pathlib import Path

import psycopg
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from botocore.exceptions import BotoCoreError, ClientError

from app.api.routes import CONSOLE_ORIGINS
from app.pipeline import store_s3
from app.research import pack_routes, pack_store, store

# Config
HQ_TENANT = Path(__file__).resolve().parents[2] / "samples" / "hq_tenant.json"
OPEN_ROLES = {"founder", "research"}  # the same rule as the console's canView for the research area (frontend/lib/auth.ts)


def load_people(path: Path = HQ_TENANT) -> dict:
    """The people who may sign in, read from the one file the HQ lane reads them from."""
    return json.loads(path.read_text())["people"]


def may_open(person: dict) -> bool:
    return bool(OPEN_ROLES & set(person.get("roles", [])))


# --- The app

def postgres_packs(connection: psycopg.Connection) -> pack_store.PostgresPacks:
    return pack_store.PostgresPacks(connection, store_s3.S3ObjectStore(store_s3.connect()))


def create_research_app(connect=store.connect, people: dict | None = None, make_packs=postgres_packs) -> FastAPI:
    """The Lab's API. The store connects on first use, so a Postgres outage never stops the product from starting."""
    app = FastAPI(title="finebrain research lab")
    app.add_middleware(CORSMiddleware, allow_origins=CONSOLE_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    people = people if people is not None else load_people()
    held: dict = {"connection": None}

    def check(persona: str) -> None:
        if persona not in people:
            raise HTTPException(401, "unknown_persona")
        if not may_open(people[persona]):
            raise HTTPException(403, "research_not_allowed")

    def connection() -> psycopg.Connection:
        # Reuse a live connection; a broken one is dropped so the next request tries again
        if held["connection"] is not None and not held["connection"].closed:
            return held["connection"]
        held["connection"] = connect()
        return held["connection"]

    def packs() -> pack_store.PostgresPacks:
        return make_packs(connection())

    @app.exception_handler(HTTPException)
    async def as_error(request: Request, error: HTTPException) -> JSONResponse:
        body = error.detail if isinstance(error.detail, dict) else {"error": error.detail}  # an audit refusal carries its audits
        return JSONResponse(body, status_code=error.status_code)

    @app.exception_handler(psycopg.Error)
    @app.exception_handler(BotoCoreError)
    @app.exception_handler(ClientError)
    async def store_down(request: Request, error: Exception) -> JSONResponse:
        """Postgres or S3 did not answer: say so, and connect afresh on the next request."""
        held["connection"] = None
        return JSONResponse({"error": "research_store_unavailable"}, status_code=503)

    @app.get("/status")
    def status(x_persona: str = Header(default="")) -> dict:
        """Lab on, and whether its store answers. Store down is a state the console shows, not an error."""
        check(x_persona)
        try:
            ready = store.schema_ready(connection())
        except psycopg.Error:
            held["connection"] = None
            ready = False
        return {"lab": "enabled", "store": "ready" if ready else "unavailable"}

    pack_routes.register(app, check, packs)
    return app
