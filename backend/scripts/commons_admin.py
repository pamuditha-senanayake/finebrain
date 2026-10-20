# commons_admin.py: a dev script for the shared commons admin (step 13e). Loads a collection from samples/commons/ into
# Postgres once, where every tenant that links to it reads it; tenants never write it. Uses Voyage embeddings when
# VOYAGE_API_KEY is set (as Finebase HQ does), else the test stand-in.
#   uv run python -m scripts.commons_admin load lk_tax_labour
#   uv run python -m scripts.commons_admin list
# Uses: commons.py, store_postgres.py, store_chunks_pg.py, embeddings.py, fakes.py.
import os
import sys

from app.pipeline import commons, embeddings, fakes, store_postgres
from app.pipeline.store_chunks_pg import PostgresChunks


def collections(connection) -> list[tuple[str, int]]:
    rows = connection.execute("SELECT tenant_id, count(*) FROM chunks WHERE tenant_id LIKE %s GROUP BY tenant_id ORDER BY 1", (f"{commons.PREFIX}%",))
    return [(tenant, count) for tenant, count in rows]


def main() -> None:
    # Step 1: what to do
    action, collection = (sys.argv[1:] + ["list", ""])[:2]
    connection = store_postgres.connect()

    # Step 2: load one collection, or list what is stored
    if action == "load" and collection:
        embed = embeddings.voyage_embed if os.environ.get("VOYAGE_API_KEY") else fakes.fake_embed
        loaded = commons.load(PostgresChunks(connection, commons.store_id(collection)), embed, collection)
        print(f"Loaded {loaded} items into {commons.store_id(collection)} ({'Voyage' if embed is embeddings.voyage_embed else 'test'} embeddings)")
    for tenant, count in collections(connection):
        print(f"{tenant}: {count} items")


if __name__ == "__main__":
    main()
