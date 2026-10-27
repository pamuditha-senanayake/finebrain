# main.py: the API on port 8000 (uv run fastapi dev app/main.py). Serves Finebase HQ to the console and takes captures.
# Uses: api/hq.py, research/routes.py (only when RESEARCH_LAB=enabled). Reads backend/.env first, because pipeline modules read their settings when imported.
# The HQ lane is built when the server starts, never on import: fastapi dev's reloader parent imports this file only to
# find `app`, and a lane built there would consume the same Kafka topics as the worker's and handle every message twice.
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

# Config
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path) -> None:
    """Copy KEY=VALUE lines into the environment, without overriding what is already set. Values are never printed."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, _, value = line.strip().partition("=")
        if key and not key.startswith("#") and value:
            os.environ.setdefault(key.strip(), value.strip())


load_env(ENV_PATH)
RESEARCH_LAB = os.environ.get("RESEARCH_LAB", "disabled") == "enabled"  # off: no research routes, no research tables touched

from app.api import hq  # noqa: E402  (after the environment is loaded)


@asynccontextmanager
async def serve_hq(app: FastAPI):
    """Build Finebase HQ's lane in the serving process and hand every request to its app."""
    app.mount("/", hq.build_hq_app())
    yield


app = FastAPI(title="finebrain API", lifespan=serve_hq)
if RESEARCH_LAB:  # mounted before HQ's "/", so /research reaches the Lab; HQ never imports research code
    from app.research.routes import create_research_app  # noqa: E402

    app.mount("/research", create_research_app())
