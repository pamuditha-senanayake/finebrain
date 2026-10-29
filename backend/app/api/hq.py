# hq.py: builds the Finebase HQ pipeline the API serves: seed and people from samples, real infra where it answers,
# real Claude and Voyage when keys are set, and a background loop that keeps the clock moving and every consumer running.
# Another tenant (Finebase HQ-2) is served by a second process with HQ_TENANT_FILE=hq2_tenant.json; its file names its own sample files.
# Used by: main.py. Uses: conn_inbound.py, orchestrate.py, adapters.py, llm.py, fakes.py, routes.py, ready_notices.py, nightly.py, distiller.py, temporal_ready.py, temporal_nightly.py. Reads env: HQ_REAL_PARTS, HQ_USE_CLAUDE, HQ_VOICE_FIX.
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.api import distiller, grants, nightly, ready_notices, self_knowledge, studio_approvals
from app.api.studio_seed import extend_seed
from app.api.routes import create_api_app
from app.pipeline import conn_call, conn_inbound, fakes, llm, orchestrate, temporal_nightly, temporal_ready
from app.pipeline.adapters import ALL_REAL_PARTS, make_memory_adapters, missing_infra, real_adapters
from app.pipeline.observe import log_event

# Config
SAMPLES = Path(__file__).resolve().parents[2] / "samples"
REAL_PARTS_SETTING = os.environ.get("HQ_REAL_PARTS", "auto")  # auto: every part that answers; none: all in memory; or a comma list
USE_CLAUDE = os.environ.get("HQ_USE_CLAUDE", "on") != "off"
VOICE_FIX = os.environ.get("HQ_VOICE_FIX", "on" if USE_CLAUDE else "off") != "off"  # Haiku fixing misheard words costs about $0.0003 a question, so it can stay on when the rest of Claude is off
TENANT_FILE = os.environ.get("HQ_TENANT_FILE", "hq_tenant.json")  # HQ-2 sets hq2_tenant.json on its own port
DEFAULT_TENANT = "finebase-hq"
TICK_SECONDS = 0.2
STUDIO_MAX_TOKENS = 3000  # a drafted story with six cases needs room
EXTRACT_MAX_TOKENS = 4000  # one window of a document can state a few dozen facts


def load_hq() -> tuple[dict, dict]:
    """The golden seed with Finebase HQ's tenant id, people and clusters on top, the brain's knowledge about itself, the
    sample obligations readiness watches (step 16), and sample weekly counts for the spike check (step 15)."""
    hq = json.loads((SAMPLES / TENANT_FILE).read_text())
    files = hq.get("sample_files", {})  # a tenant besides HQ names its own files; HQ's stay the defaults
    golden = json.loads((SAMPLES / "golden_refund_run.json").read_text())
    world = json.loads((SAMPLES / files["world"]).read_text()) if "world" in files else {}  # connectors, skills, agents, policy and knowledge that replace the golden ones
    knowledge = world.get("knowledge", golden["seed"]["knowledge"]) + list(self_knowledge.items())
    readiness = json.loads((SAMPLES / files.get("obligations", "hq_obligations.json")).read_text())
    learning = json.loads((SAMPLES / files.get("counts", "hq_counts.json")).read_text())
    return extend_seed({**golden["seed"], **world, **hq["seed_overrides"], "people": hq["people"], "knowledge": knowledge, "readiness": readiness,
                        "sample_counts": learning, "timezone": hq["tenant"]["timezone"]}, hq), hq


def choose_parts() -> frozenset[str]:
    """Which connectors run for real. auto takes every part that answers right now, so the API starts without Docker too."""
    if REAL_PARTS_SETTING == "none":
        parts = frozenset()
    elif REAL_PARTS_SETTING == "auto":
        parts = ALL_REAL_PARTS - set(missing_infra(ALL_REAL_PARTS))
    else:
        parts = frozenset(part.strip() for part in REAL_PARTS_SETTING.split(",") if part.strip())
    return parts | ({"voyage"} if USE_CLAUDE and os.environ.get("VOYAGE_API_KEY") else set())


def topic_prefix(seed: dict) -> str:
    """Finebase HQ keeps its plain topic names; any other tenant gets its own, so two tenants never read each other's messages."""
    return "" if seed["tenant_id"] == DEFAULT_TENANT else f"{seed['tenant_id']}."


def choose_models():
    """Real Claude for S2 (an upload's domain), S3, S6 and S7 when a key is set; otherwise a model that declines, so every case
    escalates to a person, and uploads are filed under general."""
    if USE_CLAUDE and os.environ.get("ANTHROPIC_API_KEY"):
        return llm.make_tool_caller(), llm.make_chooser(), llm.make_grader(), llm.make_chooser(system=llm.DOMAIN_SYSTEM)
    return fakes.make_recorded_caller({})[0], None, None, None


def choose_answerer():
    """Claude Haiku for Lisena when a key is set, because answers are short and spoken, so speed matters most; None lists the closest documents instead."""
    return llm.make_answerer(model=llm.FAST_MODEL) if USE_CLAUDE and os.environ.get("ANTHROPIC_API_KEY") else None


def choose_writer():
    """Claude Haiku that fixes misheard words in a spoken question when a key is set; None keeps the words as heard."""
    return llm.make_writer() if VOICE_FIX and os.environ.get("ANTHROPIC_API_KEY") else None


def choose_chatter():
    """Claude Sonnet with tools for the Studio assistant when a key is set; None answers with a pointer to the forms."""
    return llm.make_tool_caller(max_tokens=STUDIO_MAX_TOKENS) if USE_CLAUDE and os.environ.get("ANTHROPIC_API_KEY") else None


def choose_extractor():
    """Claude Haiku with the fact tool for S11 when a key is set; None files documents without proposing facts."""
    return llm.make_tool_caller(model=llm.FAST_MODEL, max_tokens=EXTRACT_MAX_TOKENS) if USE_CLAUDE and os.environ.get("ANTHROPIC_API_KEY") else None


def choose_resolver():
    """Claude Opus with the resolution tool for S12 conflicts when a key is set; None lets the newer source win."""
    return llm.make_tool_caller(model=llm.CAREFUL_MODEL) if USE_CLAUDE and os.environ.get("ANTHROPIC_API_KEY") else None


def set_now(lane) -> datetime:
    """Real time, on the lane and its bus. Returns it."""
    now = datetime.now(timezone.utc)
    lane.bus.now = now
    return now


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
            studio_approvals.sweep(lane)  # C4 Studio changes merge once their cooling period ends
            grants.sweep(lane)  # C4 data source grants become active once theirs ends (step 16)
            lane.bus.drain()
        except Exception as error:  # the loop must outlive any one bad message; the bus already dead-letters failures
            log_event("API", "loop_error", error=type(error).__name__)
        time.sleep(TICK_SECONDS)


def build_hq_app():
    """The API app for Finebase HQ, with its pipeline running in the background."""
    seed, hq = load_hq()
    parts = choose_parts()
    model, choose, grade, classify = choose_models()
    make_adapters = real_adapters(parts, topic_prefix=topic_prefix(seed)) if parts else make_memory_adapters
    lane = orchestrate.build_lane(seed, model, None, datetime.now(timezone.utc),  # no stand-in gateway: refunds go to the shop's database
                                   make_adapters, choose, grade, new_id=unique_id,
                                   classify=classify, extract=choose_extractor(), resolve=choose_resolver())
    lane.tooling["send_email"] = None  # no stand-in sender: replies go into the customer's chat (tools_chat.py), or to a person
    if hasattr(lane.bus, "tick"):  # a long Kafka drain keeps the clock true, so waits, refunds and records carry the real time
        lane.bus.tick = lambda: setattr(lane, "now", set_now(lane))
    chatter = choose_chatter()
    if lane.runner is not None:  # S15's hourly tick (step 16) and S13's 02:00 review (step 15) on Temporal; without it, Check now and Run now
        temporal_ready.start(lane.runner, lane.seed["tenant_id"], lambda: ready_notices.run_check(lane, "schedule"))
        zone = lane.seed["timezone"]
        temporal_nightly.start(lane.runner, lane.seed["tenant_id"], zone, lambda: {"date": nightly.review(lane, chatter, lane.resolve, "schedule")["date"]})
        temporal_nightly.start_distiller(lane.runner, lane.seed["tenant_id"], zone, lambda: distiller.distill(lane, lane.extract, "schedule"))  # step 13d
    log_event("API", "hq_started", parts=sorted(parts), claude=choose is not None)
    threading.Thread(target=keep_running, args=(lane,), daemon=True).start()
    conn_call.note_roles(lane)  # connections saved before roles existed get theirs, so runs find the shop database by key
    conn_inbound.start(lane)  # live connections' customer messages come in through S1
    return create_api_app(lane, hq, choose_answerer(), chatter, choose_writer())
