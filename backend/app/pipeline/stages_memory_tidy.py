# stages_memory_tidy.py: the living memory's night (stage 5d), one step of the Distiller at 03:00. Traces older than 30 days
# move to cold (archived in S3 first, then out of Postgres, still readable by id); near-identical patterns merge into the
# bigger one; patterns idle for 90 days are archived and removed, freeing room in their area's budget; areas near their
# budget and patterns growing in Other are reported for a person. One worker tidies a tenant once a night.
# Used by: api/distiller.py, tests/test_memory_tidy.py. Uses: stages_memory.py (near patterns), stages_memory_flow.py (AREAS),
# store_patterns.py, stages_normalize.py (claim).
import gzip
import json
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.pipeline import stages_memory as memory
from app.pipeline.contracts_memory import TraceRecord
from app.pipeline.stages_memory_flow import AREAS
from app.pipeline.stages_normalize import claim
from app.pipeline.store_patterns import ALWAYS_ON, PATTERN_BUDGET, Pattern

# Config: Docs/CB_Living_Memory_Architecture.md sections 6, 9 and 13
RUN_KIND = "memory_tidy"  # records kind keyed by the night's date
WARM_DAYS = 30
IDLE_DAYS = 90
NEAR_BUDGET = PATTERN_BUDGET - 5
OTHER_WEEKS = 4
OTHER_GROWING = 10  # traces in the last OTHER_WEEKS that make a pattern in Other worth a person's look
BATCH = 500
MAX_BATCHES = 20  # a night moves at most 10,000 traces; a backlog finishes over the next nights


class MemoryTidy(BaseModel):
    night: str
    by: str
    frozen: int
    merged: int
    dropped: int
    areas_near_budget: list[str]
    growing_in_other: list[dict]


# --- Cold traces

def cold_uri(lane, kind: str, item_id: str) -> str:
    return f"s3://brain/{lane.seed['tenant_id']}/memory/{kind}/{item_id}.json.gz"


def freeze_traces(lane, now: datetime) -> int:
    """Archive first, then leave the warm tier, so a crash between the two loses nothing; the next night finishes it."""
    frozen = 0
    for _ in range(MAX_BATCHES):
        batch = lane.traces.older_than(now - timedelta(days=WARM_DAYS), BATCH)
        for trace in batch:
            lane.object_store[cold_uri(lane, "traces", trace.trace_id)] = gzip.compress(trace.model_dump_json().encode())
            frozen += lane.traces.remove(trace.trace_id)
        if len(batch) < BATCH:
            break
    return frozen


def cold_trace(lane, trace_id: str) -> TraceRecord | None:
    """A trace that left the warm tier, read back from S3 by its id."""
    try:
        return TraceRecord.model_validate_json(gzip.decompress(lane.object_store[cold_uri(lane, "traces", trace_id)]))
    except KeyError:
        return None


def scrub_cold(lane, trace_id: str, note: str) -> bool:
    """Forgetting reaches cold traces too: replace a frozen trace's why lines in S3. False when there is none or nothing changed."""
    trace = cold_trace(lane, trace_id)
    if trace is None or trace.why == [note]:
        return False
    lane.object_store[cold_uri(lane, "traces", trace_id)] = gzip.compress(trace.model_copy(update={"why": [note]}).model_dump_json().encode())
    return True


# --- Patterns

def alike(a: Pattern, b: Pattern) -> bool:
    """Same skill, ending and policy check, and at most one step apart: the same way of working, counted twice."""
    head, other = a.key.split("|"), b.key.split("|")
    return head[1] == other[1] and head[3:] == other[3:] and memory.steps_apart(a.steps, b.steps) <= memory.NEAR_MATCH_STEPS


def merge_area(lane, area: str) -> int:
    """Each smaller pattern folds into the biggest one it is alike, so the bigger one keeps its id and its history."""
    survivors: list[Pattern] = []
    merged = 0
    for pattern in sorted(lane.patterns.area_patterns(area).values(), key=lambda p: (-p.count, p.key)):
        twin = next((s for s in survivors if alike(s, pattern)), None)
        if twin:
            lane.patterns.merge(area, twin.key, pattern.key)
            merged += 1
        else:
            survivors.append(pattern)
    return merged


def drop_idle(lane, area: str, now: datetime) -> int:
    """A pattern whose newest trace is older than IDLE_DAYS is archived, then removed. One with no traces yet was just confirmed: kept."""
    dropped = 0
    for pattern in list(lane.patterns.area_patterns(area).values()):
        weeks = lane.patterns.weeks(pattern.pattern_id)
        if not weeks or max(weeks) >= (now - timedelta(days=IDLE_DAYS)).date():
            continue
        lane.object_store[cold_uri(lane, "patterns", pattern.pattern_id)] = gzip.compress(json.dumps({"area": area, **vars(pattern), "weeks": {str(w): c for w, c in weeks.items()}}).encode())
        dropped += bool(lane.patterns.remove(area, pattern.key))
    return dropped


def growing_in_other(lane, now: datetime) -> list[dict]:
    """Patterns in Other busy enough that a person should move them into an area of their own."""
    since = (now - timedelta(weeks=OTHER_WEEKS)).date()
    found = []
    for pattern in lane.patterns.area_patterns(ALWAYS_ON).values():
        recent = sum(count for week, count in lane.patterns.weeks(pattern.pattern_id).items() if week >= since)
        if recent >= OTHER_GROWING:
            found.append({"pattern_id": pattern.pattern_id, "steps": pattern.steps, "recent": recent})
    return sorted(found, key=lambda f: -f["recent"])


# --- The night

def tidy(lane, by: str) -> dict:
    """One night of the living memory. A second call the same night, or a second worker, changes nothing."""
    night = lane.now.date().isoformat()
    done = lane.records.load(RUN_KIND, night)
    if done:
        return done
    if not claim(lane.memory_claims, f"tidy:{night}"):
        return {"night": night, "skipped": "another worker is tidying tonight"}
    # Step 1: old traces to cold, then patterns merged and idle ones dropped, area by area
    frozen = freeze_traces(lane, lane.now)
    merged = sum(merge_area(lane, area) for area in sorted(AREAS))
    dropped = sum(drop_idle(lane, area, lane.now) for area in sorted(AREAS))
    # Step 2: what a person should look at, then keep the night
    near = [area for area in sorted(AREAS) if len(lane.patterns.area_patterns(area)) >= NEAR_BUDGET]
    result = MemoryTidy(night=night, by=by, frozen=frozen, merged=merged, dropped=dropped, areas_near_budget=near, growing_in_other=growing_in_other(lane, lane.now))
    lane.records.save(RUN_KIND, night, result)
    return result.model_dump(mode="json")
