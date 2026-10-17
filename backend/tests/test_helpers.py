# test_helpers.py: the shared helpers every stage uses: retry and counters.
# DLQ replay is tested on both buses in test_bus.py. Uses: app/pipeline/retry.py, app/pipeline/observe.py.
import pytest

from app.pipeline import observe
from app.pipeline.retry import call_with_retry


class Flaky:
    """Fails a set number of times, then succeeds."""

    def __init__(self, failures: int, error: Exception):
        self.failures, self.error, self.calls = failures, error, 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "ok"


def is_timeout(error: Exception) -> bool:
    return isinstance(error, TimeoutError)


def test_retryable_error_is_tried_again_with_growing_waits():
    action, waits = Flaky(2, TimeoutError()), []
    assert call_with_retry(action, is_timeout, sleep=waits.append) == "ok"
    assert action.calls == 3 and waits == [0.2, 0.4]


def test_other_errors_are_raised_at_once():
    action = Flaky(1, ValueError("bad arguments"))
    with pytest.raises(ValueError):
        call_with_retry(action, is_timeout, sleep=lambda _: None)
    assert action.calls == 1


def test_gives_up_after_the_last_attempt():
    action = Flaky(10, TimeoutError())
    with pytest.raises(TimeoutError):
        call_with_retry(action, is_timeout, attempts=6, sleep=lambda _: None)
    assert action.calls == 6


def test_counters_add_up_and_reset():
    observe.reset_counts()
    observe.count("s1.captured")
    observe.count("s1.captured", 2)
    assert observe.read_count("s1.captured") == 3
    observe.reset_counts()
    assert observe.read_count("s1.captured") == 0
