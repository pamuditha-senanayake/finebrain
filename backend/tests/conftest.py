# conftest.py: one rule for every test file. Tests on real infra make throwaway tenants named test_...; when the session
# ends, what they left in Postgres, S3 and Valkey is removed, so the dev database holds only real tenants (step 13 slice 0).
# Uses: scripts/clean_test_tenants.py.
import pytest

from scripts.clean_test_tenants import clean


@pytest.fixture(scope="session", autouse=True)
def clean_test_tenants_after():
    yield
    clean(apply=True)
