# store_valkey.py: Valkey key sets for "seen before" checks: S2 dedup keys and the buses' handled events.
# Used by: tests/test_keyset.py, orchestrate.py and the buses from step 6. Uses: nothing local.
# Caches and rate limits come when stages get thicker (step 7).
import os
from collections.abc import Iterator, MutableSet

import valkey

# Config
VALKEY_URL = os.environ.get("VALKEY_URL", "redis://localhost:6379/0")
SEEN_TTL_SECONDS = 7 * 24 * 3600  # reference doc section 7: idempotency keys live up to 7 days


def connect(url: str = VALKEY_URL) -> valkey.Valkey:
    """Open a client that returns strings, not bytes."""
    return valkey.Valkey.from_url(url, decode_responses=True, socket_connect_timeout=2)


def valkey_is_up(url: str = VALKEY_URL) -> bool:
    """True when Valkey answers, so tests can skip cleanly when Docker is down.
    A port that accepts but never replies (Docker hung) times out and counts as down, not a crash."""
    try:
        probe = valkey.Valkey.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        return bool(probe.ping())
    except valkey.ValkeyError:
        return False


class ValkeyKeySet(MutableSet[str]):
    """Behaves like the set S2 uses, so stages do not change when this is swapped in.
    One Valkey key per member, so each member expires on its own clock."""

    def __init__(self, client: valkey.Valkey, namespace: str, ttl_seconds: int = SEEN_TTL_SECONDS):
        self.client = client
        self.namespace = namespace  # for example "finebase_labs:s2_dedup"
        self.ttl_seconds = ttl_seconds

    def key_for(self, member: str) -> str:
        return f"{self.namespace}:{member}"

    def __contains__(self, member: object) -> bool:
        return bool(self.client.exists(self.key_for(str(member))))

    def add(self, member: str) -> None:
        self.client.set(self.key_for(member), "1", ex=self.ttl_seconds)

    def claim(self, member: str) -> bool:
        """Add only if absent, in one step. True means this caller got it first, so two workers never both act."""
        return bool(self.client.set(self.key_for(member), "1", ex=self.ttl_seconds, nx=True))

    def discard(self, member: str) -> None:
        self.client.delete(self.key_for(member))

    def __iter__(self) -> Iterator[str]:
        prefix = self.namespace + ":"
        return iter(sorted(key.removeprefix(prefix) for key in self.client.scan_iter(match=prefix + "*")))

    def __len__(self) -> int:
        return sum(1 for _ in self)
