# lane.py: Lane, everything one pipeline holds: seed, adapters, model and in-flight state. Data only.
# Used by: orchestrate.py (builds it), run_steps.py, run_approvals.py, temporal_flow.py (act on it). Uses: fakes.py (types).
from dataclasses import dataclass, field
from datetime import datetime

from app.pipeline.fakes import Gateway, Model


@dataclass
class Lane:
    """Everything one pipeline holds. Data only; orchestrate.py, run_steps.py and run_approvals.py act on it."""
    seed: dict
    model: Model
    gateway: Gateway | None  # a stand-in refund gateway for stage tests; None in production, where refunds go to the shop (tools_write.py)
    now: datetime
    new_id: object
    bus: object
    object_store: object
    vault: object
    seen_keys: object
    records: object
    graph: object
    chunks: object
    embed: object
    rerank: object
    check_access: object
    tooling: dict  # S9: rate limiter, finished results, email sender, how to wait between retries
    audit: object  # S10: hash-chained audit log
    broadcaster: object  # S10: live ui.events for the console stream
    entities: object  # step 13a: the entity registry (store_entities.py)
    counts: object = None  # step 15: weekly counts for the spike check (store_counts.py)
    uses: object = None  # step 13c: which runs and answers cited which items (store_uses.py)
    commons: list = field(default_factory=list)  # step 13e: the linked commons collections, read only (commons.py)
    grade: object = None  # S7 grader (llm.make_grader); defaults to the fake that passes cited rationales
    choose: object = None  # S3 tie-break (llm.make_chooser); None means close calls go unrouted
    classify: object = None  # S2 domain of an upload (llm.make_chooser with DOMAIN_SYSTEM); None files it under general
    extract: object = None  # S11 fact extraction (llm.make_tool_caller on Haiku); None proposes no facts
    resolve: object = None  # S12 conflict proposals (llm.make_tool_caller on Opus); None lets the newer source win
    runner: object = None  # TemporalRunner, or None to run tasks in-process
    signals: dict = field(default_factory=dict)  # signal_id to K2, so S4 can read entities
    approvals: dict = field(default_factory=dict)  # approval_id to its cause and task
    pending: dict = field(default_factory=dict)  # approval_id to a paused run (in-process only)
    waiting: dict = field(default_factory=dict)  # run_id to when its wait for the customer ends (in-process only; Temporal keeps its own timer)
