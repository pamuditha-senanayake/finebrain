# clean_test_tenants.py: a dev script. Tests that use real infra make throwaway tenants named test_...; this removes what
# they left in Postgres (every table with a tenant_id), S3 (keys under test_...) and Valkey (keys test_...). Real tenants are
# never touched. It only counts unless told to delete:
#   uv run python -m scripts.clean_test_tenants          (dry run: what would go)
#   uv run python -m scripts.clean_test_tenants --apply  (delete)
# tests/conftest.py runs it with apply after every test session. Uses: store_postgres.py, store_s3.py, store_valkey.py.
import sys

from app.pipeline import store_postgres, store_s3, store_valkey

# Config
TEST_PATTERNS = ("test\\_%",)
S3_PREFIX = "test_"
VALKEY_PATTERN = "test_*"


def tables_with_tenants(connection) -> list[str]:
    rows = connection.execute("SELECT table_name FROM information_schema.columns WHERE column_name = 'tenant_id' AND table_schema = 'public' ORDER BY 1")
    return [row[0] for row in rows]


def clean_postgres(apply: bool) -> dict[str, int]:
    """Rows of test tenants, per table."""
    connection = store_postgres.connect()
    where = " OR ".join("tenant_id LIKE %s" for _ in TEST_PATTERNS)
    verb = "DELETE" if apply else "SELECT count(*)"
    counted = {}
    for table in tables_with_tenants(connection):
        result = connection.execute(f"{verb} FROM {table} WHERE {where}", TEST_PATTERNS)  # table names come from the catalog, not from input
        counted[table] = result.rowcount if apply else result.fetchone()[0]
    return {table: n for table, n in counted.items() if n}


def clean_s3(apply: bool) -> int:
    """Objects whose key starts with a test tenant's prefix."""
    client = store_s3.connect()
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=store_s3.S3_BUCKET, Prefix=S3_PREFIX)
    keys = [item["Key"] for page in pages for item in page.get("Contents", [])]
    for start in range(0, len(keys), 1000) if apply else []:  # S3 deletes at most 1000 keys per call
        client.delete_objects(Bucket=store_s3.S3_BUCKET, Delete={"Objects": [{"Key": key} for key in keys[start:start + 1000]]})
    return len(keys)


def clean_valkey(apply: bool) -> int:
    client = store_valkey.connect()
    keys = list(client.scan_iter(match=VALKEY_PATTERN, count=1000))
    if apply and keys:
        client.delete(*keys)
    return len(keys)


def clean(apply: bool) -> dict:
    """Clean every store that answers. Returns what was (or would be) removed."""
    found = {}
    if store_postgres.database_is_up():
        found["postgres"] = clean_postgres(apply)
    if store_s3.s3_is_up():
        found["s3_objects"] = clean_s3(apply)
    if store_valkey.valkey_is_up():
        found["valkey_keys"] = clean_valkey(apply)
    return found


if __name__ == "__main__":
    applying = "--apply" in sys.argv
    print(("Deleted: " if applying else "Would delete (dry run, add --apply): ") + str(clean(applying)))
