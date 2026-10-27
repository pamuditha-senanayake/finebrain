# access.py: K6 access checks at the moment of action. Ask OPA (fail closed: no answer means deny), or run the
# same rules in Python for memory runs. Used by: adapters.py, stages_govern.py, tests. Uses: contracts_reason.py, observe.py.
# The rules here mirror backend/infra/opa/access.rego; tests run the same cases on both so they cannot drift.
import os
from collections.abc import Callable

import httpx

from app.pipeline.contracts_reason import AccessCheck
from app.pipeline.observe import count, log_event

# Config
OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")
DECISION_PATH = "/v1/data/finebrain/access/decision"
TIMEOUT_SECONDS = 0.5  # the design target is 10 ms; slower than this counts as unreachable
ALL_SENSITIVITIES = {"public", "internal", "confidential", "restricted"}
READABLE = {"L1": ALL_SENSITIVITIES, "L2": ALL_SENSITIVITIES, "L3": {"public", "internal", "confidential"}}
OPEN_CAPABILITIES = {"escalate"}
FAIL_CLOSED = {"allow": False, "rule_id": "opa_unreachable", "reason": "access service did not answer, so the action is denied"}

Checker = Callable[[AccessCheck], dict]


def build_input(check: AccessCheck, people: dict) -> dict:
    """The OPA input. The person acted for is resolved to a tier here; an unknown person gets none."""
    person_tier = people.get(check.on_behalf_of, {}).get("tier") if check.on_behalf_of else None
    return {
        "principal": {"capabilities": check.principal.capabilities, "tier": check.principal.tier},
        "action": check.action, "resource": {"sensitivity": check.resource.sensitivity},
        "on_behalf_of": check.on_behalf_of, "on_behalf_of_tier": person_tier,
    }


def evaluate(rules_input: dict) -> dict:
    """The access.rego rules in Python. First failing check wins, so every deny names its reason."""
    principal, sensitivity = rules_input["principal"], rules_input["resource"]["sensitivity"]
    if rules_input["action"] not in OPEN_CAPABILITIES and rules_input["action"] not in principal["capabilities"]:
        return {"allow": False, "rule_id": "missing_capability", "reason": "principal lacks this capability"}
    if sensitivity not in READABLE.get(principal["tier"], set()):
        return {"allow": False, "rule_id": "sensitivity_by_tier", "reason": "data too sensitive for this tier"}
    if rules_input["on_behalf_of"] is not None and sensitivity not in READABLE.get(rules_input["on_behalf_of_tier"], set()):
        return {"allow": False, "rule_id": "on_behalf_of", "reason": "the person acted for may not see this data"}
    return {"allow": True, "rule_id": "capability_and_tier", "reason": "capability held and data readable"}


TIER_ORDER = ["L3", "L2", "L1"]  # lowest first


def effective_tier(principal_tier: str, on_behalf_of: str | None, people: dict) -> str:
    """Acting for a person, the agent carries no more than that person may: the lower of the two tiers."""
    person_tier = people.get(on_behalf_of, {}).get("tier") if on_behalf_of else None
    tiers = [t for t in (principal_tier, person_tier) if t in TIER_ORDER]
    return min(tiers, key=TIER_ORDER.index) if tiers else principal_tier


def make_memory_checker(people: dict) -> Checker:
    return lambda check: evaluate(build_input(check, people))


def ask_opa(rules_input: dict, url: str) -> dict:
    """One OPA query. Any failure, or no result, is a deny."""
    try:
        response = httpx.post(url + DECISION_PATH, json={"input": rules_input}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        result = response.json().get("result")
    except Exception as error:  # fail closed: an access service we cannot reach never means yes
        count("s7.opa_unreachable")
        log_event("S7", "opa_unreachable", error=type(error).__name__)
        return FAIL_CLOSED
    return result or FAIL_CLOSED


def make_opa_checker(people: dict, url: str = OPA_URL) -> Checker:
    return lambda check: ask_opa(build_input(check, people), url)


def opa_is_up(url: str = OPA_URL) -> bool:
    """True when OPA answers, so tests can skip cleanly when Docker is down."""
    try:
        return httpx.get(url + "/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False
