# grade_freshness.py: grades one freshness answer by rule, never by a model (spec rule R7). An answer is fresh when it
# states the expected value, stale when it states a superseded one instead, mixed when it states both, refused when it says
# the context has no answer, and wrong otherwise. Numbers match by value (within the gold tolerance) with their unit words;
# text matches when every content word of the gold value appears. Used by: research/runner.py. Uses: nothing local.
import re

# Config
REFUSAL = "NOT_IN_CONTEXT"  # what the Execution_V1 answer prompt tells the model to say
NUMBER = re.compile(r"\d+(?:\.\d+)?")
SYMBOLS = {"%": " percent ", "$": " dollars "}
FILLER = {"a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "by", "with", "at"}


def normalized(text: str) -> str:
    for symbol, word in SYMBOLS.items():
        text = text.replace(symbol, word)
    return re.sub(r"(?<=\d),(?=\d{3})", "", text.lower())  # 1,000 reads as 1000


def unit_words(value: str) -> set[str]:
    """The non-number words of a value, singular, without filler: '5 business days' gives {'business', 'day'}."""
    return {word.rstrip("s") for word in re.findall(r"[a-z]+", normalized(value)) if word not in FILLER}


def states(answer: str, value: str, tolerance: float = 0.0) -> bool:
    """True when the answer states this value."""
    wanted, said = NUMBER.findall(normalized(value)), normalized(answer)
    words = {word.rstrip("s") for word in re.findall(r"[a-z]+", said)}
    if not wanted:
        return bool(unit_words(value)) and unit_words(value) <= words
    numbers = [float(n) for n in NUMBER.findall(said)]
    return all(any(abs(float(n) - got) <= tolerance for got in numbers) for n in wanted) and unit_words(value) <= words


def grade(answer: str, expected: str, superseded: list[str], tolerance: float = 0.0) -> str:
    """fresh, stale, mixed, refused or wrong."""
    if REFUSAL in answer:
        return "refused"
    fresh = states(answer, expected, tolerance)
    stale = any(states(answer, old, tolerance) for old in superseded)
    if fresh and stale:
        return "mixed"
    return "fresh" if fresh else "stale" if stale else "wrong"
