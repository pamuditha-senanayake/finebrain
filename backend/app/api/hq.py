# hq.py: builds the Finebase HQ pipeline the API serves: seed and people from samples, real infra where it answers,
# real Claude and Voyage when keys are set, and a background loop that keeps the clock moving and every consumer running.
# Used by: main.py. Uses: orchestrate.py, adapters.py, llm.py, fakes.py, routes.py. Reads env: HQ_REAL_PARTS, HQ_USE_CLAUDE.
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.api.routes import create_api_app
from app.pipeline import fakes, llm, orchestrate
from app.pipeline.adapters import ALL_REAL_PARTS, make_memory_adapters, missing_infra, real_adapters
from app.pipeline.observe import log_event

# Config
SAMPLES = Path(__file__).resolve().parents[2] / "samples"
REAL_PARTS_SETTING = os.environ.get("HQ_REAL_PARTS", "auto")  # auto: every part that answers; none: all in memory; or a comma list
USE_CLAUDE = os.environ.get("HQ_USE_CLAUDE", "on") != "off"
TICK_SECONDS = 0.2


def load_hq() -> tuple[dict, dict]:
    """The golden seed with Finebase HQ's tenant id, people and clusters on top."""
    hq = json.loads((SAMPLES / "hq_tenant.json").read_text())
    golden = json.loads((SAMPLES / "golden_refund_run.json").read_text())
    return {**golden["seed"], **hq["seed_overrides"], "people": hq["people"]}, hq


def choose_parts() -> frozenset[str]:
    """Which connectors run for real. auto takes every part that answers right now, so the API starts without Docker too."""
    if REAL_PARTS_SETTING == "none":
        parts = frozenset()
    elif REAL_PARTS_SETTING == "auto":
        parts = ALL_REAL_PARTS - set(missing_infra(ALL_REAL_PARTS))
    else:
        parts = frozenset(part.strip() for part in REAL_PARTS_SETTING.split(",") if part.strip())
    return parts | ({"voyage"} if USE_CLAUDE and os.environ.get("VOYAGE_API_KEY") else set())


def choose_models():
    """Real Claude for S3, S6 and S7 when a key is set; otherwise a model that declines, so every case escalates to a person."""
    if USE_CLAUDE and os.environ.get("ANTHROPIC_API_KEY"):
        return llm.make_tool_caller(), llm.make_chooser(), llm.make_grader()
    return fakes.make_recorded_caller({})[0], None, None


def choose_answerer():
    """Claude Sonnet for Ask the Brain when a key is set; None lists the closest documents instead."""
    return llm.make_answerer() if USE_CLAUDE and os.environ.get("ANTHROPIC_API_KEY") else None


def unique_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def keep_running(lane) -> None:
    """Background loop: move the pipeline's clock to now, expire overdue approvals (in-process runs), deliver queued messages."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            if lane.runner is None:
                orchestrate.sweep_expired(lane, now)
            else:
                lane.now = lane.bus.now = now
            lane.bus.drain()
        except Exception as error:  # the loop must outlive any one bad message; the bus already dead-letters failures
            log_event("API", "loop_error", error=type(error).__name__)
        time.sleep(TICK_SECONDS)


def build_hq_app():
    """The API app for Finebase HQ, with its pipeline running in the background."""
    seed, hq = load_hq()
    parts = choose_parts()
    model, choose, grade = choose_models()
    make_adapters = real_adapters(parts) if parts else make_memory_adapters
    lane = orchestrate.build_lane(seed, model, fakes.make_fake_gateway()[0], datetime.now(timezone.utc), make_adapters, choose, grade, new_id=unique_id)
    log_event("API", "hq_started", parts=sorted(parts), claude=choose is not None)
    threading.Thread(target=keep_running, args=(lane,), daemon=True).start()
    return create_api_app(lane, hq, choose_answerer())
