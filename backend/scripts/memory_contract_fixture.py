# memory_contract_fixture.py: records the HQ API's real answers for every Living memory path into
# samples/memory_live_answers.json, so the frontend's own zod contracts can parse them (frontend/tests/unit/memory-live.test.ts).
# The golden refunds run through the HQ API in memory; a drift flag and a skill draft are added so every shape has data.
# Run from backend/:  uv run python scripts/memory_contract_fixture.py   (again after any change to a memory shape)
# Uses: api/routes.py, api/memory_views.py, stages_memory_drift.py, tests/test_api.py (how the golden emails are sent).
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from fastapi.testclient import TestClient

from app.api.routes import create_api_app
from app.pipeline import capture_api, fakes, orchestrate
from app.pipeline import stages_memory_drift as drift
from app.pipeline.contracts_memory import DriftFix, DriftFlag, DriftSubject, SkillDraft
from tests.golden import NOW, RAW, recorded_answers
from tests.test_api import FOUNDER, HQ, SEED

# Config
OUT = Path("samples/memory_live_answers.json")
EMAILS = ("s2_refund_monthly_in_policy", "s3_refund_annual_late_large")


def build():
    """HQ over a memory pipeline that has handled the two golden emails, plus one drift and one skill draft."""
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], fakes.make_fake_gateway()[0], NOW)
    client = TestClient(create_api_app(lane, HQ))
    for key in EMAILS:
        body = RAW[key]["raw_body"].encode()
        headers = {"content-type": "message/rfc822", "x-external-id": RAW[key]["external_id"], "x-signature": capture_api.sign(SEED["connectors"]["conn_gmail_support"]["secret"], body)}
        client.post("/capture/conn_gmail_support", content=body, headers=headers)
        lane.bus.drain()
    trace_id = lane.bus.topics["traces.recorded"][0].payload["trace_id"]
    drift.raise_drift(lane, DriftFlag(flag_id="dr-policy-policy_refund", tenant_id=SEED["tenant_id"], kind="policy", area="customer_care",
                                      subject=DriftSubject(type="policy", id="policy_refund", name="policy_refund"), summary="People work outside this policy more often",
                                      usual=1, latest=9, evidence_trace_ids=[trace_id], state="detected", fix=DriftFix(summary="Refund window: up to 45 days", change_request_id=None),
                                      recheck=None, reopened_note=None, raised_at=NOW))
    lane.records.save(drift.DRAFT_KIND, "xs-1", SkillDraft(draft_id="xs-1", tenant_id=SEED["tenant_id"], area="customer_care", pattern_id="pt-1", steps=["order_checked", "refund_by_hand"],
                                                           support=24, same_outcome_share=0.96, follow_rate=0.9, state="draft", change_request_id=None, created_at=NOW))
    lane.bus.drain()
    return client, trace_id


def main() -> int:
    client, trace_id = build()
    paths = ["memory", "memory/areas/customer_care", "memory/traces", "memory/traces?flag=surprise", "memory/traces?flag=drift", f"memory/traces/{trace_id}", "memory/drifts", "memory/skills"]
    answers = {}
    for path in paths:
        response = client.get(f"/api/t/{SEED['tenant_id']}/{path}", headers={"x-persona": FOUNDER})
        if response.status_code != 200:
            print(f"{path}: {response.status_code} {response.text[:200]}")
            return 1
        answers[path] = response.json()
    OUT.write_text(json.dumps(answers, indent=1, sort_keys=True))
    print(f"wrote {len(answers)} answers to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
