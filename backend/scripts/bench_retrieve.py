# bench_retrieve.py: step 13b proof. Grows a throwaway tenant's chunks on real Postgres (random vectors, no API calls) and
# times S5's two searches with and without a scope, at each size. Scoped work should stay flat while unscoped grows.
# Run from backend/ with Docker up:  uv run python -m scripts.bench_retrieve            (10,000 then 100,000 chunks)
#                                    uv run python -m scripts.bench_retrieve 5000 20000 (any sizes)
# The tenant is deleted at the end. Uses: store_postgres.py, store_chunks_pg.py.
import random
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone

from app.pipeline import store_postgres
from app.pipeline.store_chunks_pg import EMBEDDING_SIZE, PostgresChunks, scope_filter

# Config
SIZES = [int(size) for size in sys.argv[1:]] or [10_000, 100_000]
PER_CASE = 100  # chunks about each case; growth brings new cases, as new customers do, so the case count grows with size
GENERAL = 50  # the first chunks are general knowledge (policies), tagged with no entity; their number does not grow
BATCH = 10_000
RUNS = 25
KINDS = ["chunk"]
GROW = """
INSERT INTO chunks (tenant_id, item_id, kind, body, recorded_at, embedding, domain, entity_ids)
SELECT %(tenant)s, 'b_' || i, 'chunk',
       jsonb_build_object('item_id', 'b_' || i, 'kind', 'chunk', 'text', 'Note ' || i || ' about refund case ' || (i / %(per_case)s),
                          'source', jsonb_build_object('document_id', 'bench', 'uri', 'bench'), 'recorded_at', '2026-01-01T00:00:00+00:00',
                          'valid_from', null, 'valid_to', null, 'verified_by', null, 'version_ref', null, 'score', 0, 'sensitivity', 'internal'),
       '2026-01-01T00:00:00+00:00',
       random_vector.v,
       'customer_care',
       CASE WHEN i < %(general)s THEN '{}'::text[] ELSE ARRAY['ent_' || (i / %(per_case)s)] END
FROM generate_series(%(start)s::int, %(stop)s::int) AS i,
     LATERAL (SELECT array_agg(random())::vector AS v FROM generate_series(1, %(size)s::int) WHERE i IS NOT NULL) AS random_vector
"""


# --- Helpers

def grow(chunks: PostgresChunks, start: int, stop: int) -> None:
    """Add chunks start..stop-1 in batches, built inside Postgres so nothing large crosses the wire."""
    for low in range(start, stop, BATCH):
        params = {"tenant": chunks.tenant_id, "per_case": PER_CASE, "size": EMBEDDING_SIZE, "general": GENERAL, "start": low, "stop": min(low + BATCH, stop) - 1}
        chunks.connection.execute(GROW, params)
    chunks.connection.execute("VACUUM ANALYZE chunks")  # flushes the GIN pending lists, as autovacuum does in normal running


def timed(search, cases: int) -> tuple[float, float]:
    """p50 and p95 in milliseconds over RUNS calls, each for a random case."""
    took = []
    for _ in range(RUNS):
        started = time.perf_counter()
        search(f"ent_{random.randrange(1, cases)}")
        took.append((time.perf_counter() - started) * 1000)
    return statistics.median(took), statistics.quantiles(took, n=20)[-1]


def slice_size(chunks: PostgresChunks, entity_id: str) -> int:
    """How many chunks one case's scope holds: its own, plus general knowledge."""
    scope = {"domains": ["customer_care"], "entity_ids": [entity_id]}
    query = f"SELECT count(*) FROM chunks WHERE tenant_id = %(tenant)s AND {scope_filter(scope)}"
    return chunks.connection.execute(query, chunks.filters(KINDS, None, None, 0, scope)).fetchone()[0]


def measure(chunks: PostgresChunks, size: int) -> dict:
    now, vector = datetime.now(timezone.utc), [random.random() for _ in range(EMBEDDING_SIZE)]
    scope, cases = lambda entity_id: {"domains": ["customer_care"], "entity_ids": [entity_id]}, size // PER_CASE
    return {
        "size": size, "slice": slice_size(chunks, "ent_7"),
        "vector_all": timed(lambda _: chunks.by_vector(vector, KINDS, now, now, 20), cases),
        "vector_scoped": timed(lambda e: chunks.by_vector(vector, KINDS, now, now, 20, scope(e)), cases),
        "text_all": timed(lambda _: chunks.by_text("refund case", KINDS, now, now, 20), cases),
        "text_scoped": timed(lambda e: chunks.by_text("refund case", KINDS, now, now, 20, scope(e)), cases),
    }


def report(rows: list[dict]) -> None:
    print("\n| Chunks | One case's slice | Meaning search, all | Meaning search, scoped | Word search, all | Word search, scoped |")
    print("|---|---|---|---|---|---|")
    for row in rows:
        cells = [f"{row[key][0]:.1f} / {row[key][1]:.1f} ms" for key in ("vector_all", "vector_scoped", "text_all", "text_scoped")]
        print(f"| {row['size']:,} | {row['slice']:,} | " + " | ".join(cells) + " |")
    print("\nEach cell is p50 / p95 over", RUNS, "searches.")


def main() -> None:
    # Step 1: a throwaway tenant
    chunks = PostgresChunks(store_postgres.connect(), f"bench_{uuid.uuid4().hex[:8]}")
    rows, stored = [], 0
    try:
        # Step 2: grow to each size, then time both searches with and without a scope
        for size in sorted(SIZES):
            print(f"growing to {size:,} chunks ...", flush=True)
            grow(chunks, stored, size)
            stored = size
            rows.append(measure(chunks, size))
        report(rows)
    finally:
        # Step 3: leave nothing behind
        chunks.connection.execute("DELETE FROM chunks WHERE tenant_id = %s", (chunks.tenant_id,))


if __name__ == "__main__":
    main()
