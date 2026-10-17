# retry.py: try again. call_with_retry retries a failed call; replay_dead_letters resends failed messages.
# Used by: S9 Act and other stages as they get thicker, tests. Uses: a bus (bus_memory.py or bus_kafka.py).
import time
from collections.abc import Callable
from typing import TypeVar

# Config
DEFAULT_ATTEMPTS = 6  # reference doc section 8: retryable tool errors get up to 6 attempts
BASE_DELAY_SECONDS = 0.2

T = TypeVar("T")


def attempt_once(action: Callable[[], T], is_retryable: Callable[[Exception], bool]) -> tuple[bool, T | None]:
    """(True, result) on success, (False, None) on a retryable error. Other errors are raised at once."""
    try:
        return True, action()
    except Exception as error:
        if not is_retryable(error):
            raise
        return False, None


def call_with_retry(
    action: Callable[[], T], is_retryable: Callable[[Exception], bool],
    attempts: int = DEFAULT_ATTEMPTS, base_delay: float = BASE_DELAY_SECONDS, sleep=time.sleep,
) -> T:
    """Run action, retrying retryable errors with backoff. The last attempt raises its own error."""
    for attempt in range(attempts - 1):
        done, result = attempt_once(action, is_retryable)
        if done:
            return result
        sleep(base_delay * 2 ** attempt)  # 0.2s, 0.4s, 0.8s ...
    return action()


def replay_dead_letters(bus, topic: str) -> int:
    """After a fix, send each failed original back with its own event_id. Returns how many were sent."""
    letters = bus.dead_letters(topic)
    for letter in letters:
        bus.redeliver(topic, letter.original)
    return len(letters)
