# test_memory_stores.py: stage 5a of the living memory. The trace store and the pattern store keep every rule, in memory
# always and on Postgres when it answers: one area per read, a budget of 50 patterns, a trace counted once however often
# it arrives, pages that never repeat or skip, Other always on. Two workers at once give one result on Postgres.
# Uses: app/pipeline/store_traces.py, store_patterns.py, stages_memory.py, store_postgres.py, tests/test_memory_skeleton.py.
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest

from app.pipeline import stages_memory as memory
from app.pipeline import store_postgres
from app.pipeline.store_patterns import PATTERN_BUDGET, MemoryPatterns, PostgresPatterns
from app.pipeline.store_traces import MemoryTraces, PostgresTraces
from tests.test_memory_skeleton import NOW, stripe_refund, trace

# Config
POSTGRES_UP = store_postgres.database_is_up()
WEEK = date(2026, 10, 26)  # the Monday of NOW's week


def tenant() -> str:
    return f"test_memory_{uuid.uuid4().hex[:8]}"


def pattern_stores():
    yield MemoryPatterns
    if POSTGRES_UP:
        yield lambda t: PostgresPatterns(store_postgres.connect(), t)


def trace_stores():
    yield MemoryTraces
    if POSTGRES_UP:
        yield lambda t: PostgresTraces(store_postgres.connect(), t)


# --- Patterns

@pytest.mark.parametrize("make", list(pattern_stores()), ids=["memory", "postgres"][: 1 + POSTGRES_UP])
def test_patterns_count_each_trace_once_and_keep_five_examples(make):
    store = make(tenant())
    first = trace("r1")
    pattern = memory.confirm(first, store)
    assert memory.confirm(first, store).pattern_id == pattern.pattern_id  # the same key is the same pattern
    for n in range(7):
        memory.triage(trace(f"r{n}"), store)
    memory.triage(trace("r3"), store)  # a redelivery
    kept = store.area_patterns("customer_care")[memory.pattern_key(first)]
    assert kept.count == 7 and len(kept.examples) == 5 and kept.examples[0] == "tr-r6"
    assert store.weeks(pattern.pattern_id) == {WEEK: 7}


@pytest.mark.parametrize("make", list(pattern_stores()), ids=["memory", "postgres"][: 1 + POSTGRES_UP])
def test_an_area_holds_at_most_its_budget(make):
    store = make(tenant())
    added = [memory.confirm(stripe_refund(n, outcome=f"ending {n}"), store) for n in range(PATTERN_BUDGET + 1)]
    assert all(added[:-1]) and added[-1] is None
    assert len(store.area_patterns("customer_care")) == PATTERN_BUDGET
    assert store.area_patterns("finance") == {}  # another area is untouched and read on its own


@pytest.mark.parametrize("make", list(pattern_stores()), ids=["memory", "postgres"][: 1 + POSTGRES_UP])
def test_an_area_turned_off_sends_its_work_to_other_which_never_turns_off(make):
    store = make(tenant())
    assert store.switch_area("customer_care", False) and not store.switch_area("general", False)
    assert not store.area_on("customer_care") and store.area_on("general") and store.area_on("sales")
    assert memory.triage(trace("r1"), store).area == "general"


@pytest.mark.skipif(not POSTGRES_UP, reason="no Postgres on localhost:5433")
def test_two_workers_never_both_add_the_last_pattern_or_count_a_trace_twice():
    who = tenant()
    stores = [PostgresPatterns(store_postgres.connect(), who) for _ in range(2)]
    for n in range(PATTERN_BUDGET - 1):
        memory.confirm(stripe_refund(n, outcome=f"ending {n}"), stores[0])
    # Step 1: both workers race for the 50th place with different patterns; exactly one gets it
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda i: memory.confirm(stripe_refund(100 + i, outcome=f"race {i}"), stores[i]), range(2)))
    assert sum(r is not None for r in results) == 1 and len(stores[0].area_patterns("customer_care")) == PATTERN_BUDGET
    # Step 2: both count the same trace at once; it counts once
    pattern = next(r for r in results if r)
    with ThreadPoolExecutor(2) as pool:
        counted = list(pool.map(lambda i: stores[i].count(pattern, WEEK, "tr-same"), range(2)))
    assert counted.count(True) == 1 and stores[0].weeks(pattern.pattern_id) == {WEEK: 1}


# --- Traces

@pytest.mark.parametrize("make", list(trace_stores()), ids=["memory", "postgres"][: 1 + POSTGRES_UP])
def test_a_trace_is_kept_once_and_read_back_whole(make):
    store = make(tenant())
    kept = trace("r1")
    assert store.save(kept) and not store.save(kept)
    assert store.get("tr-r1") == kept and store.get("tr-missing") is None


@pytest.mark.parametrize("make", list(trace_stores()), ids=["memory", "postgres"][: 1 + POSTGRES_UP])
def test_pages_walk_one_area_newest_first_without_repeats_or_gaps(make):
    store = make(tenant())
    for n in range(60):
        store.save(stripe_refund(n).model_copy(update={"started_at": NOW - timedelta(minutes=n)}))
    store.save(trace("r1").model_copy(update={"area": "finance"}))
    seen, cursor = [], None
    while True:
        page, cursor = store.page("customer_care", cursor)
        seen += [t.trace_id for t in page]
        if not cursor:
            break
    assert seen == [f"tr-stripe-{n}" for n in range(60)]  # newest first, each once, finance never mixed in
    assert [t.trace_id for t in store.page("finance")[0]] == ["tr-r1"]
