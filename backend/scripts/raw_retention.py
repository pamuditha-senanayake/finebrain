# raw_retention.py: a dev script, the dry run for raw retention (step 13c). Lists the raw bodies of a tenant in S3 whose
# 90 days have ended, which the nightly memory pass will delete (leaving tombstones and an audit entry). It deletes nothing.
#   uv run python -m scripts.raw_retention               (Finebase HQ)
#   uv run python -m scripts.raw_retention other-tenant
# Uses: store_s3.py, stages_cold.py (expired_raw).
import sys
from datetime import datetime, timezone

from app.pipeline import stages_cold, store_s3

# Config
DEFAULT_TENANT = "finebase-hq"


def main() -> None:
    # Step 1: every object the tenant has in S3
    tenant = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TENANT
    store = store_s3.S3ObjectStore(store_s3.connect(), prefix=f"{tenant}/")
    uris = list(store)

    # Step 2: the raw bodies past retention
    due = stages_cold.expired_raw(uris, datetime.now(timezone.utc))
    raw = [uri for uri in uris if "/raw/" in uri]
    print(f"{tenant}: {len(raw)} raw bodies, {len(due)} past {stages_cold.RAW_DAYS} days (dry run, nothing deleted)")
    for uri in due[:20]:
        print(f"  would delete {uri}")


if __name__ == "__main__":
    main()
