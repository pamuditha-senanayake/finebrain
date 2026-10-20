# field_dictionary.py: the core field dictionary (step 13d). Every fact, whatever document or form it came from, is read
# into the same five core fields, so analysis always compares like with like: who it is about, what is stated, when, the
# amount, and the outcome. A value that fits none of them (a duration, a plain text) is kept as a named extra field. It is
# worked out from the fact's subject, predicate and value, so facts from before have it too.
# Used by: api/vault_views.py, tests/test_dupes.py. Uses: nothing local.

# Config
CORE = ("who", "what", "when", "amount", "outcome")
WHEN_TYPES = {"date"}
AMOUNT_TYPES = {"money", "number", "percent", "quantity"}


def core_of(fact: dict, who: str) -> dict:
    """{"core": the five fields (None where the fact says nothing), "extra": named fields that fit none}. who: the subject's name."""
    value = fact.get("value") or {}
    kind, said = value.get("type", ""), value.get("normalized") or value.get("raw")
    when = said if kind in WHEN_TYPES else str(fact.get("valid_from") or "")[:10] or None  # a fact about a date, or else since when it holds
    core = {"who": who or None, "what": (fact.get("predicate") or "").replace("_", " ") or None, "when": when,
            "amount": said if kind in AMOUNT_TYPES else None, "outcome": None}  # a fact states, it does not end; runs carry outcomes
    extra = {kind: said} if kind and said and kind not in WHEN_TYPES | AMOUNT_TYPES else {}
    return {"core": core, "extra": extra}
