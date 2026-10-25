# test_chain.py: stages chained through the in-memory bus, with S4 running each task.
# Uses: app/pipeline/orchestrate.py, app/pipeline/fakes.py, tests/golden.py.
from app.pipeline import fakes, orchestrate
from app.pipeline.contracts_run import Decision
from tests.golden import NOW, SEED, golden, raw_sample, recorded_answers


# --- Helpers

def make_lane():
    """A fresh pipeline whose model answers s2 and s3 as in the golden runs. Returns it and the payments made."""
    gateway, paid = fakes.make_fake_gateway()
    return orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], gateway, NOW), paid


def run_sample(key: str):
    """Capture one raw sample and let every consumer catch up."""
    lane, paid = make_lane()
    orchestrate.capture_signal(lane, raw_sample(key))
    lane.bus.drain()
    return lane, paid


def payloads(lane, topic: str) -> list[dict]:
    """Payloads published on one topic, oldest first."""
    return [envelope.payload for envelope in lane.bus.topics.get(topic, [])]


# --- Chains

def test_s1_to_s3_shares_one_correlation():
    lane, _ = run_sample("s2")
    chain = [lane.bus.topics[topic][0] for topic in ("signals.raw", "signals.normalized", "tasks.created")]
    assert payloads(lane, "tasks.created")[0]["activity_id"] == golden("s2", "TaskRequest")["activity_id"]
    assert len({envelope.correlation_id for envelope in chain}) == 1
    assert [envelope.causation_id for envelope in chain[1:]] == [envelope.event_id for envelope in chain[:-1]]


def test_s2_refund_is_paid_and_resolved():
    lane, paid = run_sample("s2")
    assert [result["status"] for result in payloads(lane, "actions.executed")] == ["succeeded"]
    assert payloads(lane, "runs.completed")[-1]["outcome"] == "resolved"
    assert len(paid) == 1 and "approvals.requested" not in lane.bus.topics


def test_s3_waits_for_approval_then_pays():
    # Step 1: the run pauses at S8 and nothing is paid
    lane, paid = run_sample("s3")
    approval = payloads(lane, "approvals.requested")[0]
    assert approval["dri_id"] == golden("s3", "ApprovalRequest")["dri_id"]
    assert payloads(lane, "runs.completed")[-1]["outcome"] == "awaiting_approval" and paid == {}

    # Step 2: the Head of Customer Success approves, and the run resumes
    orchestrate.decide(lane, Decision(approval_id=approval["approval_id"], decision="approve", decided_by=["head_of_cs"], decided_at=NOW))
    lane.bus.drain()
    assert len(paid) == 1 and payloads(lane, "runs.completed")[-1]["outcome"] == "resolved"


def test_s3_rejected_never_pays():
    lane, paid = run_sample("s3")
    approval_id = payloads(lane, "approvals.requested")[0]["approval_id"]
    orchestrate.decide(lane, Decision(approval_id=approval_id, decision="reject", decided_by=["head_of_cs"], decided_at=NOW))
    lane.bus.drain()
    assert paid == {} and payloads(lane, "runs.completed")[-1]["outcome"] == "blocked"


def test_invoice_chat_goes_to_unrouted():
    lane, paid = run_sample("s4")
    assert len(payloads(lane, "tasks.unrouted")) == 1
    assert "tasks.created" not in lane.bus.topics and paid == {}


def test_broken_chat_body_goes_to_dead_letter():
    lane, _ = make_lane()
    orchestrate.capture_signal(lane, {**raw_sample("s4"), "external_id": "chat_bad", "raw_body": "{not json"})
    lane.bus.drain()
    letters = lane.bus.topics["signals.raw.dlq"]
    assert [(letter.stage, letter.error_code, letter.retryable) for letter in letters] == [("S2", "ParseError", False)]
    assert "signals.normalized" not in lane.bus.topics


def test_same_event_is_handled_once():
    lane, paid = run_sample("s2")
    lane.bus.redeliver("signals.raw", lane.bus.topics["signals.raw"][0])
    lane.bus.drain()
    assert len(payloads(lane, "tasks.created")) == 1 and len(paid) == 1


def test_s4_starts_the_run_that_s5_to_s10_finish():
    # Contract S4 to S5: one runs.started, before S5's first read, carrying the run id the record closes with
    lane, _ = run_sample("s2")
    started, completed = payloads(lane, "runs.started"), payloads(lane, "runs.completed")
    assert len(started) == 1 and started[0]["run_id"] == completed[-1]["run_id"] == payloads(lane, "access.decisions")[0]["run_id"]
    assert lane.bus.topics["runs.started"][0].event_id < lane.bus.topics["access.decisions"][0].event_id  # evt_0004 style ids count up
    assert started[0]["handoff"] is None and started[0]["recipe"]["skill_ref"] == payloads(lane, "tasks.created")[0]["skill_ref"]  # s2 is an email
