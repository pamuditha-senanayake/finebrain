# test_memory_views.py: stage 7 of the living memory, the page on live data. The HQ API answers every memory path in the
# page's camelCase shapes, from the traces of the golden refunds; a steward confirms a surprise as normal; a skill drafted
# from traces is sent to an L1 user as a new skill; a workspace without the memory stores says not connected yet.
# Uses: app/api/memory_views.py, memory_fixes.py, routes.py, tests/test_api.py (the hq fixture), tests/studio_helpers.py.
from app.api import memory_views
from app.pipeline import stages_memory_drift as drift
from app.pipeline.contracts_memory import SkillDraft
from tests.studio_helpers import FOUNDER as STUDIO_FOUNDER
from tests.studio_helpers import REFUND_WF, build, op
from tests.test_api import FOUNDER, get, hq  # noqa: F401  (the fixture: s2 resolved, s3 waiting for approval)

# Config
MAP_KEYS = {"tenantId", "asOf", "isSample", "areas", "totals"}
AREA_KEYS = {"key", "name", "enabled", "traces7d", "tracesTotal", "patterns", "patternBudget", "skills", "drift", "surprises", "outsidePolicy"}
TRACE_KEYS = {"id", "area", "source", "subject", "startedAt", "endedAt", "outcome", "patternId", "match", "policyCheck", "drift", "runId"}


def test_the_map_counts_live_traces_in_the_pages_shape(hq):  # noqa: F811  (the hq fixture, imported)
    client, _, _ = hq
    found = get(client, "memory").json()
    assert set(found) == MAP_KEYS and found["isSample"] is False and len(found["areas"]) == 8
    assert set(found["areas"][0]) == AREA_KEYS and found["totals"]["traces7d"] >= 1 and found["totals"]["surprises"] >= 1


def test_an_area_shows_its_patterns_and_drift(hq):  # noqa: F811  (the hq fixture, imported)
    client, _, _ = hq
    area = get(client, "memory/areas/customer_care").json()
    assert area["area"]["key"] == "customer_care" and area["drifts"] == [] and isinstance(area["patterns"], list)


def test_traces_page_and_one_trace_read_start_to_end(hq):  # noqa: F811  (the hq fixture, imported)
    client, _, _ = hq
    page = get(client, "memory/traces?area=customer_care").json()
    assert page["total"] >= 1 and set(page["items"][0]) == TRACE_KEYS and page["items"][0]["subject"]
    surprises = get(client, "memory/traces?flag=surprise").json()
    assert surprises["total"] >= 1 and all(item["match"] == "surprise" for item in surprises["items"])
    detail = get(client, f"memory/traces/{page['items'][0]['id']}").json()
    assert detail["steps"] and detail["policies"][0]["id"] == "policy_refund" and detail["access"][0]["ruleId"]


def test_a_steward_confirms_a_surprise_as_normal_once(hq):  # noqa: F811  (the hq fixture, imported)
    client, lane, _ = hq
    trace_id = get(client, "memory/traces?flag=surprise").json()["items"][0]["id"]
    answer = client.post(f"/api/t/{lane.seed['tenant_id']}/ops/memoryConfirm", json={"traceId": trace_id}, headers={"x-persona": FOUNDER})
    assert answer.status_code == 200 and answer.json()["patternId"]
    assert get(client, f"memory/traces/{trace_id}").json()["match"] == "normal"
    assert trace_id not in [i["id"] for i in get(client, "memory/traces?flag=surprise").json()["items"]]
    again = client.post(f"/api/t/{lane.seed['tenant_id']}/ops/memoryConfirm", json={"traceId": trace_id}, headers={"x-persona": FOUNDER})
    assert again.status_code == 409 and again.json()["error"] == "already_answered"


def test_a_skill_drafted_from_traces_is_sent_to_an_l1_user_as_a_new_skill():
    client, lane = build()
    draft = SkillDraft(draft_id="xs-1", tenant_id=lane.seed["tenant_id"], area="customer_care", pattern_id="pt-1", steps=["order_checked", "refund_by_hand"],
                       support=24, same_outcome_share=0.96, follow_rate=0.9, state="draft", change_request_id=None, created_at=lane.now)
    lane.records.save(drift.DRAFT_KIND, "xs-1", draft)
    sent = op(client, "memorySendDraft", {"draftId": "xs-1", "workflowId": REFUND_WF}, STUDIO_FOUNDER)
    record = lane.records.load("change_request", sent.json()["changeRequestId"])
    assert sent.status_code == 200 and record["input"]["intent"] == "create" and record["criticality"] >= 3
    shown = memory_views.serve(lane, "memory/skills", {})[0]
    assert shown["state"] == "in_review" and shown["changeRequestId"] == record["cr_id"]
    assert op(client, "memorySendDraft", {"draftId": "xs-1", "workflowId": REFUND_WF}, STUDIO_FOUNDER).status_code == 409


def test_an_unknown_area_or_trace_is_not_found(hq):  # noqa: F811  (the hq fixture, imported)
    client, _, _ = hq
    assert get(client, "memory/areas/space").status_code == 404 and get(client, "memory/traces/tr-none").status_code == 404
