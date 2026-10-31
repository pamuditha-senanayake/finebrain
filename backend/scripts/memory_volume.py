# memory_volume.py: the volume run for the living memory (stage 5e). Thousands of realistic traces across the eight areas
# (steady patterns, a step more or less, rare surprises, refunds made by hand) go through triage the way the consumer runs
# it; a person confirms the first surprise of each new way of working; a tenth are redelivered. Then the night moves them
# all to cold. Since stage 6 a few traces show a rogue agent, and the drift night must raise exactly one flag for it.
# With --weeks 3 or more (stage 8), the latest week also moves the refund skill to a new path and spikes late hand refunds,
# and the night must raise exactly one skill drift and one policy drift for them.
# The rules must still hold and triage must stay inside its budget.
# Run from backend/:  uv run python scripts/memory_volume.py [traces] [--weeks N] [--real]   (--real: Postgres, Valkey and S3)
# Exit code 1 if a rule breaks or triage averages over its budget. Uses: stages_memory_flow.py, stages_memory.py,
# stages_memory_tidy.py, orchestrate.py, adapters.py, tests/golden.py.
import random
import sys
import time
import uuid
from datetime import timedelta

sys.path.insert(0, ".")
from app.pipeline import fakes, orchestrate
from app.pipeline import stages_memory as memory
from app.pipeline import stages_memory_flow as flow
from app.pipeline import stages_memory_tidy as night
from app.pipeline.adapters import make_memory_adapters, real_adapters
from app.pipeline import stages_memory_drift as drift
from app.pipeline.contracts_memory import TraceAccess, TraceRecord
from app.pipeline.store_drift import MAX_EVIDENCE
from app.pipeline.contracts_signal import VersionRef
from app.pipeline.stages_learn import week_of, zone_of
from app.pipeline.store_patterns import PATTERN_BUDGET
from tests.golden import NOW, SEED

# Config
DEFAULT_TRACES = 5000
DEFAULT_WEEKS = 2
DRIFT_WEEKS = 3  # the skill and policy checks need this much history
REAL_PARTS = frozenset({"postgres", "valkey", "s3"})
TRIAGE_BUDGET_SECONDS = 0.05  # Docs/CB_Living_Memory_Architecture.md section 13: under 50 ms a trace, no Claude call
REDELIVERED = 0.1
# Each area's usual ways of working: (skill, steps, outcome, policy check), and how often each happens
WORK = {
    "customer_care": [("refund-standard", ["context_read", "action_proposed", "access_allowed", "refund_issued"], "resolved", "within", 50),
                      ("refund-standard", ["context_read", "action_proposed", "gate_failed", "escalated"], "escalated", "outside", 10),
                      ("care-answer", ["context_read", "reply_drafted", "reply_sent"], "resolved", "within", 40)],
    "finance": [("billing-dunning", ["invoice_read", "reminder_sent"], "resolved", "within", 30), ("billing-expenses", ["receipt_read", "spend_filed"], "resolved", "within", 20)],
    "operations": [("scheduler-booking", ["calendar_read", "slot_offered", "meeting_booked"], "resolved", "within", 25)],
    "sales": [("sales-quote", ["lead_read", "quote_drafted", "quote_sent"], "resolved", "within", 15)],
    "legal": [("compliance-readiness", ["obligation_read", "evidence_checked"], "resolved", "within", 8)],
    "product": [("web-content-update", ["page_read", "change_proposed"], "resolved", "within", 6)],
    "general": [(None, ["message_read", "filed"], "resolved", "unknown", 4)],
}
OUTSIDE_SHARE = 0.05  # refunds made by hand in the shop
SURPRISE_SHARE = 0.01  # work that fits no pattern at all
ROGUE_SHARE = 0.002  # finished work whose access said deny: security drift, always the same agent
NEW_PATH = ["context_read", "plan_checked", "action_proposed", "access_allowed", "refund_issued", "customer_told"]  # two steps more, past near-match
LATE_SHARE = {"usual": 0.08, "latest": 0.85}  # hand refunds past the window, before and in the latest week
REFUND = SEED["refund_policy"]
REFUND_POLICY = memory.trace_policy({**REFUND, "_ref": REFUND["policy_ref"]})
ROGUE = TraceAccess(decision_id="d-rogue", action="refund:issue", principal_id="agent_rogue", on_behalf_of=None, decision="deny", effective_tier="internal")


def build_lane(real: bool, tag: str):
    """The memory consumers on a lane, in memory or on real stores; only triage listens, so only triage is timed."""
    seed = {**SEED, "tenant_id": f"volume_mem_{tag}"} if real else SEED
    adapters = real_adapters(REAL_PARTS) if real else make_memory_adapters
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, adapters)
    lane.bus.subscribers = {"traces.recorded": [s for s in lane.bus.subscribers["traces.recorded"] if s[0] == "memory_triage"]}
    return lane


def started_in(lane, generator: random.Random, week: int):
    """A moment in that week back from now; the latest week runs from its Monday until now, so the drift checks read it last."""
    monday = week_of(NOW, zone_of(lane))
    span = int((NOW - NOW.replace(year=monday.year, month=monday.month, day=monday.day, hour=0, minute=0)).total_seconds() // 60)
    return NOW - timedelta(weeks=week, minutes=generator.randint(0, max(60, span) if week == 0 else 60 * 24 * 6))


def hand_refund(lane, generator: random.Random, n: int, started, latest: bool) -> TraceRecord:
    """A refund made by hand in the shop, held to the refund window; late ones spike in the latest week."""
    window = REFUND["window_days"]
    late = generator.random() < LATE_SHARE["latest" if latest else "usual"]
    days = generator.randint(window + 4, window + 14) if late else generator.randint(3, window - 2)
    trace = memory.trace_of_outside(lane.seed["tenant_id"], f"shop-{n}", "customer_care", started, ["refund_by_hand"], "refunded by a person (approved)",
                                    "outside" if late else "within", [REFUND_POLICY])
    return trace.model_copy(update={"why": [f"{days} days since purchase, window is {window}"]})


def one_trace(lane, generator: random.Random, n: int, weeks: int) -> TraceRecord:
    """A realistic piece of work: mostly a steady pattern, sometimes a step more, now and then something new."""
    week = generator.randrange(weeks)
    started, latest = started_in(lane, generator, week), week == 0 and weeks >= DRIFT_WEEKS
    if generator.random() < OUTSIDE_SHARE:
        return hand_refund(lane, generator, n, started, latest)
    area = generator.choices(list(WORK), weights=[sum(w[-1] for w in ways) for ways in WORK.values()])[0]
    skill, steps, outcome, check, _ = generator.choices(WORK[area], weights=[w[-1] for w in WORK[area]])[0]
    steps = list(NEW_PATH if latest and outcome == "resolved" and skill == "refund-standard" and generator.random() < 0.7 else steps)
    if generator.random() < 0.15:
        steps.insert(generator.randint(1, len(steps) - 1), "note_added")  # one step more: still the same way of working
    if generator.random() < SURPRISE_SHARE:
        steps = [f"unusual_{generator.randint(1, 400)}", "handled"]  # something new
    ref = VersionRef(id=skill, version=1, branch="main", commit_id="c1") if skill else None
    access = [ROGUE.model_copy(update={"decision_id": f"d-rogue-{n}"})] if generator.random() < ROGUE_SHARE else []
    return TraceRecord(trace_id=f"tr-vol-{n}", tenant_id=lane.seed["tenant_id"], area=area, source="finebrain", started_at=started, ended_at=started,
                       input_ref=f"sig_vol_{n}", steps=steps, policies=[], skill=ref, access=access, outcome=outcome, decided_by="auto by policy",
                       why=[], policy_check=check, run_id=f"run_vol_{n}")


def run_traffic(lane, count: int, weeks: int, timings: list[float]) -> dict:
    """Every trace is kept and triaged; the first surprise of each new way of working is confirmed; a tenth come again."""
    generator, envelopes = random.Random(2026), []
    for n in range(count):
        trace = one_trace(lane, generator, n, weeks)
        lane.traces.save(trace)
        envelopes.append(lane.bus.publish("traces.recorded", "trace.recorded", trace, "volume"))
        started = time.perf_counter()
        lane.bus.drain()
        timings.append(time.perf_counter() - started)
        match = lane.records.load(flow.MATCH_KIND, trace.trace_id)
        if match["match"] == "surprise":
            memory.confirm(trace, lane.patterns)  # a person says: yes, this is how we work
    for envelope in generator.sample(envelopes, int(count * REDELIVERED)):
        lane.bus.handled.discard(f"memory_triage:{envelope.event_id}")  # as if another worker had never seen it (one key, never a scan)
        lane.bus.redeliver("traces.recorded", envelope)
    lane.bus.drain()
    return {"redelivered": int(count * REDELIVERED)}


def rules_hold(lane, count: int) -> list[str]:
    """Every trace matched once, no trace counted twice, every area inside its budget, one review per surprise."""
    matches = [lane.records.load(flow.MATCH_KIND, f"tr-vol-{n}") or lane.records.load(flow.MATCH_KIND, f"tr-shop-{n}") for n in range(count)]
    broken = []
    if any(m is None for m in matches):
        broken.append("a trace has no match")
    normal = sum(m["match"] == "normal" for m in matches if m)
    counted = sum(p.count for area in flow.AREAS for p in lane.patterns.area_patterns(area).values())
    if counted != normal:
        broken.append(f"patterns count {counted} traces but {normal} matched normal")
    if any(len(lane.patterns.area_patterns(area)) > PATTERN_BUDGET for area in flow.AREAS):
        broken.append("an area holds more than its budget")
    surprises = [m for m in matches if m and m["match"] == "surprise"]
    if any(len(lane.records.history(flow.REVIEW_KIND, m["trace_id"])) != 1 for m in surprises):
        broken.append("a surprise was raised for review more or less than once")
    return broken


def drift_holds(lane, count: int, weeks: int) -> tuple[list[str], float, dict]:
    """The drift night on the volume: one security flag for the one rogue agent, with its evidence, and no subject flagged twice;
    with enough weeks, one skill drift for the refund skill's new path and one policy drift for the late refunds."""
    rogues = [n for n in range(count) if (t := lane.traces.get(f"tr-vol-{n}")) and t.access and t.outcome == "resolved"]  # escalating after a deny is right, not drift
    started = time.perf_counter()
    result = drift.night(lane)
    seconds = time.perf_counter() - started
    held = lane.drift.open_flag("security", "agent_rogue")
    broken = []
    if rogues and (held is None or len(held.evidence_trace_ids) != min(len(rogues), MAX_EVIDENCE)):
        broken.append(f"security drift: {len(rogues)} rogue traces, flag {held.evidence_trace_ids if held else None}")
    subjects = [(f.kind, f.subject.id) for f in lane.drift.in_state("detected")]
    if len(subjects) != len(set(subjects)):
        broken.append("a subject has two open flags")
    if weeks >= DRIFT_WEEKS and sorted(k for k, _ in subjects if k != "security") != ["policy", "skill"]:
        broken.append(f"expected one skill and one policy drift, found {subjects}")
    return broken, seconds, {**result, "security_evidence": len(rogues)}


def night_holds(lane, count: int) -> tuple[list[str], float]:
    """Forty days later, the night moves every trace to cold, and each still reads back."""
    lane.now = NOW + timedelta(days=45)
    started = time.perf_counter()
    result = night.tidy(lane, "volume")
    seconds = time.perf_counter() - started
    total = min(count, night.BATCH * night.MAX_BATCHES)
    broken = [] if result["frozen"] == total else [f"the night moved {result['frozen']} of {total} traces"]
    # Past the night's cap the newest wait for the next night, so the rule is: every trace still reads, warm or cold
    ids = [i for n in random.Random(7).sample(range(count), 20) for i in (f"tr-vol-{n}", f"tr-shop-{n}")]
    if sum(1 for i in ids if lane.traces.get(i) or night.cold_trace(lane, i)) != 20:
        broken.append("a trace does not read back, warm or cold")
    return broken, seconds


def main() -> int:
    # Step 1: build the lane and run the traffic
    weeks = int(sys.argv[sys.argv.index("--weeks") + 1]) if "--weeks" in sys.argv else DEFAULT_WEEKS
    count = int(next((arg for i, arg in enumerate(sys.argv[1:], 1) if arg.isdigit() and sys.argv[i - 1] != "--weeks"), DEFAULT_TRACES))
    real, tag, timings = "--real" in sys.argv, uuid.uuid4().hex[:8], []
    lane = build_lane(real, tag)
    extra = run_traffic(lane, count, weeks, timings)

    # Step 2: check the rules, then the night, then the speed
    broken = rules_hold(lane, count)
    drift_broken, drift_seconds, drift_result = drift_holds(lane, count, weeks)
    night_broken, night_seconds = night_holds(lane, count)
    broken += drift_broken + night_broken
    per_trace, slowest = sum(timings) / len(timings), sorted(timings)[int(len(timings) * 0.95)]
    patterns = {area: len(lane.patterns.area_patterns(area)) for area in sorted(flow.AREAS)}
    print(f"traces {count} over {weeks} weeks ({'Postgres, Valkey, S3' if real else 'memory'}), redelivered {extra['redelivered']}, patterns per area {patterns}")
    print(f"triage {per_trace * 1000:.2f} ms per trace, p95 {slowest * 1000:.2f} ms (budget {TRIAGE_BUDGET_SECONDS * 1000:.0f} ms); drift night {drift_seconds:.1f} s {drift_result}; tidy night {night_seconds:.1f} s")
    print("rules hold" if not broken else "BROKEN: " + "; ".join(broken))
    return 0 if not broken and per_trace <= TRIAGE_BUDGET_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
