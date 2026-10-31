# test_memory_tidy.py: stage 5d of the living memory, the night. Old traces move to cold and stay readable, alike patterns
# merge without counting a trace twice, idle patterns are archived and removed, busy patterns in Other and areas near their
# budget are reported, and a night runs once. In memory always, on Postgres and S3 when they answer; then inside the Distiller.
# Uses: app/pipeline/stages_memory_tidy.py, store_traces.py, store_patterns.py, api/distiller.py, tests/test_memory_skeleton.py.
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.api import distiller
from app.pipeline import stages_memory as memory
from app.pipeline import stages_memory_tidy as night
from app.pipeline import store_postgres, store_s3
from app.pipeline.store_memory import MemoryRecords
from app.pipeline.store_patterns import MemoryPatterns, PostgresPatterns
from app.pipeline.store_traces import MemoryTraces, PostgresTraces
from tests.test_chain import run_sample
from tests.test_memory_skeleton import NOW, STRIPE_STEPS, stripe_refund

# Config
REAL = store_postgres.database_is_up() and store_s3.s3_is_up()


def lane_of(real: bool) -> SimpleNamespace:
    tenant = f"test_tidy_{uuid.uuid4().hex[:8]}"
    if real:
        connection = store_postgres.connect()
        return SimpleNamespace(seed={"tenant_id": tenant}, now=NOW, traces=PostgresTraces(connection, tenant), patterns=PostgresPatterns(connection, tenant),
                               records=store_postgres.PostgresRecords(connection, tenant), object_store=store_s3.S3ObjectStore(store_s3.connect(), prefix=f"{tenant}/"), memory_claims=set())
    return SimpleNamespace(seed={"tenant_id": tenant}, now=NOW, traces=MemoryTraces(tenant), patterns=MemoryPatterns(tenant), records=MemoryRecords(tenant), object_store={}, memory_claims=set())


WHERE = pytest.mark.parametrize("real", [False] + ([True] if REAL else []), ids=["memory", "postgres+s3"][: 1 + REAL])


def counted(lane, area: str, steps: list[str], outcome: str, days_ago: list[int]):
    """A pattern with one trace per given day, as triage would have counted them."""
    pattern = lane.patterns.add(area, "|".join([area, "none", ">".join(steps), outcome, "outside"]), steps)
    for n, days in enumerate(days_ago):
        lane.patterns.count(pattern, (NOW - timedelta(days=days)).date(), f"tr-{'-'.join(steps)}-{n}")
    return pattern


@WHERE
def test_old_traces_move_to_cold_and_stay_readable(real):
    lane = lane_of(real)
    old, recent = stripe_refund(1).model_copy(update={"started_at": NOW - timedelta(days=40)}), stripe_refund(2)
    lane.traces.save(old)
    lane.traces.save(recent)
    assert night.tidy(lane, "test")["frozen"] == 1
    assert lane.traces.get(old.trace_id) is None and night.cold_trace(lane, old.trace_id) == old
    assert lane.traces.get(recent.trace_id) == recent


@WHERE
def test_alike_patterns_merge_into_the_bigger_one_without_counting_twice(real):
    lane = lane_of(real)
    big = counted(lane, "customer_care", STRIPE_STEPS, "Refunded by a person", [1, 2, 3])
    counted(lane, "customer_care", STRIPE_STEPS[:3], "Refunded by a person", [4, 5])  # one step short: the same way of working
    counted(lane, "customer_care", ["other"], "Refunded by a person", [1])  # not alike: stays
    assert night.tidy(lane, "test")["merged"] == 1
    kept = lane.patterns.area_patterns("customer_care")
    assert len(kept) == 2 and kept[big.key].count == 5 and sum(lane.patterns.weeks(big.pattern_id).values()) == 5


@WHERE
def test_a_trace_counted_in_both_merged_patterns_still_counts_once(real):
    lane = lane_of(real)
    big = counted(lane, "customer_care", STRIPE_STEPS, "Refunded by a person", [1, 2])
    small = counted(lane, "customer_care", STRIPE_STEPS[:3], "Refunded by a person", [1])
    lane.patterns.count(small, (NOW - timedelta(days=1)).date(), f"tr-{'-'.join(STRIPE_STEPS)}-0")  # the same trace as in the big one
    lane.patterns.merge("customer_care", big.key, small.key)
    assert lane.patterns.area_patterns("customer_care")[big.key].count == 3


@WHERE
def test_idle_patterns_are_archived_and_removed_and_new_ones_kept(real):
    lane = lane_of(real)
    idle = counted(lane, "finance", ["chase", "call", "write_off"], "paid", [100, 120])  # steps far apart, so nothing merges
    counted(lane, "finance", ["remind", "pay"], "paid", [3])
    lane.patterns.add("finance", "finance|none|fresh>start|paid|within", ["fresh", "start"])  # just confirmed, no traces yet
    assert night.tidy(lane, "test")["dropped"] == 1
    assert idle.key not in lane.patterns.area_patterns("finance") and len(lane.patterns.area_patterns("finance")) == 2
    assert night.cold_uri(lane, "patterns", idle.pattern_id) in lane.object_store


@WHERE
def test_busy_patterns_in_other_and_areas_near_budget_are_reported(real):
    lane = lane_of(real)
    busy = counted(lane, "general", ["vendor_invoice"], "filed", list(range(12)))
    for n in range(night.NEAR_BUDGET):
        lane.patterns.add("sales", f"sales|none|a{n}>b{n}|won|within", [f"a{n}", f"b{n}"])  # two steps apart: never alike
    result = night.tidy(lane, "test")
    assert result["growing_in_other"][0]["pattern_id"] == busy.pattern_id and result["growing_in_other"][0]["recent"] == 12
    assert result["areas_near_budget"] == ["sales"]


@WHERE
def test_a_night_runs_once_and_a_second_worker_steps_aside(real):
    lane = lane_of(real)
    lane.traces.save(stripe_refund(1).model_copy(update={"started_at": NOW - timedelta(days=40)}))
    first = night.tidy(lane, "test")
    assert night.tidy(lane, "test") == first  # the same night again: the kept record, nothing redone
    other = lane_of(real)
    other.memory_claims.add(f"tidy:{NOW.date().isoformat()}")
    assert "skipped" in night.tidy(other, "test")


def test_the_distiller_tidies_the_living_memory_as_one_of_its_steps():
    lane, _ = run_sample("s2")
    trace = memory.TraceRecord.model_validate(lane.bus.topics["traces.recorded"][-1].payload)
    lane.traces.save(trace.model_copy(update={"trace_id": "tr-old", "started_at": lane.now - timedelta(days=45)}))
    run = distiller.distill(lane, None, "test")
    assert run["memory"]["frozen"] == 1 and night.cold_trace(lane, "tr-old") is not None
