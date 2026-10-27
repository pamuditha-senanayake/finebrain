# test_shadow_and_clock.py: what the Research Lab needs from the product (Research Lab step 2, P1 and P2), with the
# product's own behaviour unchanged. Shadow mode: a lane whose tooling mode is not "live" records every outside call with
# its exact arguments (shadow_action) and makes none: no refund in the shop, no message in a chat. A lane with no mode is
# live, as today. The clock: every stage reads the lane's clock, so a lane set to a date runs S5, S7 and S8 as of that date.
# Uses: tool_runners.py, run_finish.py, tools_chat.py, tests/s7_world.py, tests/s6_world.py, tests/test_s9_real.py.
import json
import threading
import uuid
from datetime import datetime, timedelta

import pytest

from app.pipeline import store_postgres, tool_runners, tools_chat
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.store_memory import MemoryRecords
from tests.golden import NOW
from tests.s5_world import needs_postgres, world_seed
from tests.s6_world import ask, refund, scripted
from tests.s7_world import actions, full_lane, last_record, says, verdicts
from tests.test_s1_refund_chat import FIRST, SECOND
from tests.test_s5_real import S5_PARTS, parts
from tests.test_s9_real import brain_refunds, order_status

# Config
REFUND = {"payment_ref": "pay_FB_20260930_0144", "amount_minor": 400000}
AFTER_WINDOW = datetime.fromisoformat("2026-11-15T10:00:00+05:30")  # 46 days after Anna paid, past the 30 day window
CITES_V4 = ["order:ORD-1002", "item_policy_window_v4", "item_policy_auto_limit"]  # the wording valid from 1 November


def shadow_lane(make_adapters=None, seed: dict | None = None, mode: str = "shadow"):
    """The full lane in shadow mode, with an email sender that fails the test if anything reaches it."""
    lane = full_lane(make_adapters, seed=seed)
    lane.tooling["mode"] = mode
    lane.tooling["send_email"] = lambda *call: pytest.fail(f"shadow mode sent an email: {call}")
    return lane


def shadow_calls(lane) -> list[dict]:
    return [lane.records.load(tool_runners.SHADOW_KIND, key) for key in sorted(lane.records.ids_by_kind.get(tool_runners.SHADOW_KIND, set()))]


# --- Shadow mode

def test_the_mode_fails_closed():
    assert tool_runners.is_live({}) and tool_runners.is_live({"mode": "live"})
    assert not tool_runners.is_live({"mode": "shadow"}) and not tool_runners.is_live({"mode": "Live"})


@needs_postgres
@pytest.mark.parametrize("mode", ["shadow", "shadw"])  # a mistyped mode records too: never an accidental refund
def test_anna_is_asked_then_refunded_in_shadow_and_nothing_reaches_the_shop_or_her(mode):
    lane = shadow_lane(mode=mode)
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    says(lane, SECOND)

    # Step 1: the run goes exactly as live: asked, then refunded by policy
    record = last_record(lane)
    assert (record["outcome"], record["decided_by"]) == ("resolved", "auto by policy")
    assert [status for _, status in actions(lane)] == ["succeeded", "succeeded"]

    # Step 2: both calls are recorded with their exact arguments, under S9's idempotency keys
    calls = shadow_calls(lane)
    assert [call["endpoint"] for call in calls] == ["chat", "shop_database"]
    assert calls[0]["arguments"]["message_plain"].startswith("Is it order ORD-1002")
    assert {key: calls[1]["arguments"][key] for key in ("payment_ref", "amount")} == {"payment_ref": REFUND["payment_ref"], "amount": {"amount_minor": 400000, "currency": "LKR"}}
    assert {call["idempotency_key"] for call in calls} == {e.payload["idempotency_key"] for e in lane.bus.topics["actions.executed"]}

    # Step 3: the shop's database is untouched
    assert brain_refunds() == [] and order_status() == "paid"


def test_a_retry_after_a_crash_records_the_call_once():
    records = MemoryRecords("lab_test")
    runners = tool_runners.shadow_runners(records, set(), "run_0001", NOW)
    first = runners["shop_database"]("tool_payment_refund", REFUND, "lab_test:run_0001:step_04")
    again = runners["shop_database"]("tool_payment_refund", REFUND, "lab_test:run_0001:step_04")
    assert first == again and first["external_ref"] == "shadow:lab_test:run_0001:step_04"
    assert len(records.history(tool_runners.SHADOW_KIND, "lab_test:run_0001:step_04")) == 1


def test_the_chat_door_records_a_notice_and_posts_nothing(monkeypatch):
    monkeypatch.setattr(tools_chat, "post", lambda *call: pytest.fail("shadow mode posted into a chat"))
    lane = full_lane() if store_postgres.database_is_up() else pytest.skip("Postgres is not running")
    lane.tooling["mode"] = "shadow"
    answer = tools_chat.send(lane, None, "chat_sess_anna", {"message_plain": "A person will reply here."}, "finebase_labs:run_0009:s4.handoff")
    assert answer["status"] == "succeeded"
    call = lane.records.load(tool_runners.SHADOW_KIND, "finebase_labs:run_0009:s4.handoff")
    assert (call["endpoint"], call["run_id"], call["arguments"]) == ("chat", "run_0009", {"message_plain": "A person will reply here."})


# --- Real infra

@pytest.mark.skipif(bool(missing_infra(S5_PARTS)), reason="infra not answering")
def test_shadow_on_real_infra_records_in_postgres_and_two_workers_record_once():
    tag = uuid.uuid4().hex[:8]
    lane = shadow_lane(real_adapters(parts(), topic_prefix=f"shd{tag}."), seed={**world_seed(), "tenant_id": f"test_{tag}"})

    # Step 1: Anna's two visits, the calls read back from Postgres, the shop untouched
    lane.model, _ = scripted(ask(), refund())
    says(lane, FIRST)
    says(lane, SECOND)
    refund_key = lane.bus.topics["actions.executed"][-1].payload["idempotency_key"]
    assert lane.records.load(tool_runners.SHADOW_KIND, refund_key)["arguments"]["payment_ref"] == REFUND["payment_ref"]
    assert brain_refunds() == [] and order_status() == "paid"

    # Step 2: two workers record the same new call at once: one record, no error
    runners = tool_runners.shadow_runners(lane.records, lane.tooling["claims"], "run_race", NOW)
    errors: list[Exception] = []

    def record_call() -> None:
        try:
            runners["shop_database"]("tool_payment_refund", REFUND, f"test_{tag}:run_race:step_04")
        except Exception as error:  # collected, so the test names it instead of a thread swallowing it
            errors.append(error)

    workers = [threading.Thread(target=record_call) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert errors == [] and len(lane.records.history(tool_runners.SHADOW_KIND, f"test_{tag}:run_race:step_04")) == 1


# --- The clock

@needs_postgres
def test_set_to_a_later_date_s5_reads_the_new_wording_s7_finds_the_window_closed_and_s8_dates_the_approval():
    lane = shadow_lane()
    lane.now = AFTER_WINDOW
    lane.model, _ = scripted(ask(citations=["order:ORD-1002"]), refund(citations=CITES_V4))
    says(lane, FIRST)
    says(lane, SECOND)

    # Step 1: S5 gave the agent the wording valid on 15 November, not the one closed on 1 November; S7 judged as of that day
    run_id = last_record(lane)["run_id"]
    trace = json.loads(lane.object_store[last_record(lane)["trace_object_uri"]])
    assert "item_policy_window_v4" in trace["bundle_items"] and "item_policy_window" not in trace["bundle_items"]
    policy = next(result for result in verdicts(lane)[-1]["policy_results"] if result["rule_id"] == "refund.window")
    assert policy["passed"] is False  # 46 days after payment, as of the lane's clock

    # Step 2: S8 asked a person, with dates from the lane's clock; nothing was refunded
    approval = lane.bus.topics["approvals.requested"][-1].payload
    assert AFTER_WINDOW < datetime.fromisoformat(approval["due_at"]) <= datetime.fromisoformat(approval["expires_at"]) < AFTER_WINDOW + timedelta(days=30)
    assert last_record(lane)["outcome"] == "awaiting_approval" and last_record(lane)["run_id"] == run_id
    assert all(call["endpoint"] != "shop_database" for call in shadow_calls(lane))
