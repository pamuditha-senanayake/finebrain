# bench_tiers.py: step 13 proof. A throwaway tenant keeps a fixed 10,000 live items (2,000 hot, 8,000 warm, with vectors),
# then grows by cold items only, as the nightly mover leaves them (closed or overflow: no vector, words kept). At each size it
# times S5's real searches (PostgresChunks, hot first): today's questions read hot and warm only, so they should stay flat
# however much is stored; a question about the past also reads cold and may grow. No API calls; random vectors.
# Run from backend/ with Docker up:  uv run python -m scripts.bench_tiers                   (10,000, 100,000, 500,000)
#                                    uv run python -m scripts.bench_tiers 10000 50000       (any sizes)
# The tenant is deleted at the end. Uses: store_postgres.py, store_chunks_pg.py.
import random
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone

from app.pipeline import store_postgres
from app.pipeline.store_chunks_pg import EMBEDDING_SIZE, PostgresChunks

# Config
SIZES = [int(size) for size in sys.argv[1:]] or [10_000, 100_000, 500_000]
LIVE, HOT = 10_000, 2_000  # hot and warm are budgets: they do not grow
PER_CASE = 100
BATCH = 20_000
RUNS = 25
KINDS = ["chunk"]
PAST = datetime(2026, 1, 10, tzinfo=timezone.utc)  # inside every cold item's valid time
BODY = """jsonb_build_object('item_id', 'b_' || i, 'kind', 'chunk', 'text', 'Note ' || i || ' about refund case ' || (i / %(per_case)s),
          'source', jsonb_build_object('document_id', 'bench', 'uri', 'bench'), 'recorded_at', '2026-01-01T00:00:00+00:00', 'valid_from', %(valid_from)s::text,
          'valid_to', %(valid_to)s::text, 'verified_by', null, 'version_ref', null, 'score', 0, 'sensitivity', 'internal')"""
GROW_LIVE = f"""
INSERT INTO chunks (tenant_id, item_id, kind, body, recorded_at, embedding, domain, entity_ids, tier)
SELECT %(tenant)s, 'b_' || i, 'chunk', {BODY}, '2026-01-01T00:00:00+00:00', random_vector.v, 'customer_care', ARRAY['ent_' || (i / %(per_case)s)],
       CASE WHEN i < %(hot)s THEN 'hot' ELSE 'warm' END
FROM generate_series(%(start)s::int, %(stop)s::int) AS i,
     LATERAL (SELECT array_agg(random())::vector AS v FROM generate_series(1, %(size)s::int) WHERE i IS NOT NULL) AS random_vector
"""
GROW_COLD = f"""
INSERT INTO chunks (tenant_id, item_id, kind, body, valid_from, valid_to, recorded_at, embedding, domain, entity_ids, tier)
SELECT %(tenant)s, 'b_' || i, 'chunk', {BODY}, '2026-01-01', '2026-01-15', '2026-01-01T00:00:00+00:00', NULL, 'customer_care',
       ARRAY['ent_' || (i / %(per_case)s)], 'cold'
FROM generate_series(%(start)s::int, %(stop)s::int) AS i
"""


# --- Helpers

def grow(chunks: PostgresChunks, start: int, stop: int) -> None:
    """Items start..stop-1: the first LIVE are hot or warm with vectors, the rest cold without. Built inside Postgres."""
    for sql, low_end, high_end, live in ((GROW_LIVE, start, min(stop, LIVE), True), (GROW_COLD, max(start, LIVE), stop, False)):
        for low in range(low_end, high_end, BATCH):
            params = {"tenant": chunks.tenant_id, "per_case": PER_CASE, "size": EMBEDDING_SIZE, "hot": HOT, "start": low, "stop": min(low + BATCH, high_end) - 1,
                      "valid_from": None if live else "2026-01-01T00:00:00+00:00", "valid_to": None if live else "2026-01-15T00:00:00+00:00"}
            chunks.connection.execute(sql, params)
    chunks.connection.execute("VACUUM ANALYZE chunks")


def timed(search, cases: int) -> tuple[float, float]:
    """p50 and p95 in milliseconds over RUNS calls, each about a random case."""
    took = []
    for _ in range(RUNS):
        started = time.perf_counter()
        search(f"ent_{random.randrange(1, cases)}")
        took.append((time.perf_counter() - started) * 1000)
    return statistics.median(took), statistics.quantiles(took, n=20)[-1]


def measure(chunks: PostgresChunks, size: int) -> dict:
    now, vector = datetime.now(timezone.utc), [random.random() for _ in range(EMBEDDING_SIZE)]
    scope, cases = (lambda entity_id: {"domains": ["customer_care"], "entity_ids": [entity_id]}), max(size // PER_CASE, 2)
    tiers = dict(chunks.connection.execute("SELECT tier, count(*) FROM chunks WHERE tenant_id = %s GROUP BY tier", (chunks.tenant_id,)).fetchall())
    return {
        "size": size, "live": tiers.get("hot", 0) + tiers.get("warm", 0), "cold": tiers.get("cold", 0),
        "vector_scoped": timed(lambda e: chunks.by_vector(vector, KINDS, now, now, 20, scope(e)), min(cases, LIVE // PER_CASE)),
        "text_scoped": timed(lambda e: chunks.by_text("refund case", KINDS, now, now, 20, scope(e)), min(cases, LIVE // PER_CASE)),
        "vector_tenant": timed(lambda _: chunks.by_vector(vector, KINDS, now, now, 20), cases),
        "history_scoped": timed(lambda e: chunks.by_text("refund case", KINDS, PAST, now, 20, scope(e)), cases),
    }


def report(rows: list[dict]) -> None:
    print("\n| Items stored | Hot + warm | Cold | Today, meaning, one case | Today, words, one case | Today, meaning, whole tenant | Past, words, one case |")
    print("|---|---|---|---|---|---|---|")
    for row in rows:
        cells = [f"{row[key][0]:.1f} / {row[key][1]:.1f} ms" for key in ("vector_scoped", "text_scoped", "vector_tenant", "history_scoped")]
        print(f"| {row['size']:,} | {row['live']:,} | {row['cold']:,} | " + " | ".join(cells) + " |")
    print("\nEach cell is p50 / p95 over", RUNS, "searches.")


def main() -> None:
    # Step 1: a throwaway tenant (named test_, so a test session's cleanup also finds it)
    chunks = PostgresChunks(store_postgres.connect(), f"test_bench_tiers_{uuid.uuid4().hex[:8]}")
    rows, stored = [], 0
    try:
        # Step 2: grow to each size (live first, then cold only), then time today's and the past's searches
        for size in sorted(SIZES):
            print(f"growing to {size:,} items ...", flush=True)
            grow(chunks, stored, size)
            stored = size
            rows.append(measure(chunks, size))
        report(rows)
    finally:
        # Step 3: leave nothing behind
        chunks.connection.execute("DELETE FROM chunks WHERE tenant_id = %s", (chunks.tenant_id,))


if __name__ == "__main__":
    main()
