# main.py: the API on port 8000 (uv run fastapi dev app/main.py). Serves Finebase HQ to the console and takes captures.
# Uses: api/hq.py. Reads backend/.env first, because pipeline modules read their settings when imported.
import os
from pathlib import Path

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

from app.api.hq import build_hq_app  # noqa: E402  (after the environment is loaded)

app = build_hq_app()
