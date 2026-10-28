# test_access_views.py: Security on the console is the real rules. The rules and tiers are served, a dry-run check gives the same
# answer as S7's evaluate (and names the rule), and bad input is refused plainly. Uses: tests/studio_helpers.py, api/access_views.py.
from app.pipeline import access
from tests.studio_helpers import FOUNDER, OPERATOR, TENANT, build, get

URL = f"/api/t/{TENANT}/ops/accessCheck"


def agent_of(lane) -> dict:
    return next(a for a in lane.graph.latest("agent") if a.get("capabilities"))


def ask(client, lane, **body):
    agent = agent_of(lane)
    return client.post(URL, json={"agentId": agent["_ref"]["id"], "action": agent["capabilities"][0], "sensitivity": "internal", **body}, headers={"x-persona": FOUNDER})


def test_the_rules_are_the_ones_s7_applies():
    client, lane = build()
    ids = {r["id"] for r in get(client, "access-rules")[1]}
    assert {"missing_capability", "sensitivity_by_tier", "on_behalf_of", "opa_unreachable"} <= ids


def test_the_tiers_match_what_each_tier_reads():
    client, _ = build()
    shown = {t["tier"]: set(t["reads"]) for t in get(client, "access-tiers")[1]}
    assert shown == {tier: access.READABLE[tier] for tier in ("L1", "L2", "L3")}


def test_a_held_capability_on_readable_data_is_allowed():
    client, lane = build()
    answer = ask(client, lane).json()
    assert answer["allow"] and answer["ruleId"] == "capability_and_tier"


def test_a_capability_the_agent_lacks_is_denied_with_its_rule():
    client, lane = build()
    answer = client.post(URL, json={"agentId": agent_of(lane)["_ref"]["id"], "action": "payout.send", "sensitivity": "internal"}, headers={"x-persona": FOUNDER}).json()
    assert not answer["allow"] and answer["ruleId"] == "missing_capability"


def test_acting_for_a_lower_tier_person_lowers_what_the_agent_may_read():
    client, lane = build()
    answer = ask(client, lane, sensitivity="restricted", onBehalfOf=OPERATOR).json()
    assert not answer["allow"] and answer["effectiveTier"] == "L3"


def test_bad_input_is_refused_in_plain_words():
    client, lane = build()
    assert ask(client, lane, sensitivity="secret").status_code == 400
    assert ask(client, lane, onBehalfOf="nobody").status_code == 400
    assert client.post(URL, json={"agentId": "ghost", "action": "x", "sensitivity": "internal"}, headers={"x-persona": FOUNDER}).status_code == 404


def test_a_part_can_be_opened_in_the_workflow_it_lives_in():
    client, lane = build()
    homes = get(client, "access-homes")[1]
    workflows = {w["id"] for w in get(client, "studio/workflows")[1]}
    assert homes and set(homes.values()) <= workflows
