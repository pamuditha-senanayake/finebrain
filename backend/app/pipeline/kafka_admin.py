# kafka_admin.py: topic housekeeping for the Kafka bus: is a broker up, create missing topics, and delete a test run's
# topics so they never pile up (a single-core dev broker has a partition limit). Used by: bus_kafka.py, adapters.py, tests.
from confluent_kafka.admin import AdminClient, NewTopic

# Config
DEFAULT_BOOTSTRAP = "localhost:9092"
ADMIN_TIMEOUT_SECONDS = 10


class BusUnavailable(Exception):
    """The broker would not take a topic or a message. Retrying later may work."""
    retryable = True


def broker_is_up(bootstrap: str = DEFAULT_BOOTSTRAP, timeout: float = 2.0) -> bool:
    """True when a broker answers, so tests can skip cleanly when Docker is down."""
    try:
        AdminClient({"bootstrap.servers": bootstrap}).list_topics(timeout=timeout)
    except Exception:
        return False
    return True


def create_topics(admin: AdminClient, names: list[str]) -> None:
    """Create topics with one partition. Already existing is fine; any other refusal is raised, never ignored."""
    for name, future in admin.create_topics([NewTopic(name, num_partitions=1) for name in names]).items():
        error = future.exception(ADMIN_TIMEOUT_SECONDS)
        if error is not None and "TOPIC_ALREADY_EXISTS" not in str(error):
            raise BusUnavailable(f"could not create {name}: {error}")


def delete_prefixed_topics(prefix: str, bootstrap: str = DEFAULT_BOOTSTRAP) -> int:
    """Delete every topic starting with prefix (a test run's own). Refuses an empty prefix, so real topics are safe."""
    if not prefix:
        raise ValueError("an empty prefix would delete real topics")
    admin = AdminClient({"bootstrap.servers": bootstrap})
    names = [name for name in admin.list_topics(timeout=ADMIN_TIMEOUT_SECONDS).topics if name.startswith(prefix)]
    for future in (admin.delete_topics(names).values() if names else []):
        future.exception(ADMIN_TIMEOUT_SECONDS)
    return len(names)
