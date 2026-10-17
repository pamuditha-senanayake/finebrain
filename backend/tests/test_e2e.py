# test_e2e.py: the regression test. All Lane A samples through one pipeline, checked against the
# "expected" block in pipeline_samples.json, then replayed to prove nothing happens twice.
# Runs on memory, and on real infra (REAL_PARTS) when it answers. Start infra with backend/scripts/dev_up.sh.
# Uses: app/pipeline/orchestrate.py, app/pipeline/adapters.py, app/pipeline/fakes.py, tests/golden.py.
import uuid

import pytest

from app.pipeline import fakes, orchestrate
from app.pipeline.adapters import make_memory_adapters, missing_infra, real_adapters
from app.pipeline.contracts_run import Decision
from tests.golden import NOW, RAW, SEED, golden, recorded_answer

# Config: s1 is a policy document for Lane B (S11 ingest), which is not built yet
LANE_A_SAMPLES = [sample_id for sample_id in RAW if not sample_id.startswith("s1_")]
ACTION_STEP_ID = "step_04"
REAL_PARTS = frozenset({"s3", "postgres"})  # grows one connector at a time in step 6


# --- Helpers

@pytest.fixture(params=["memory", "real"])
def setup(request):
    """(seed, adapter builder) per mode. Real runs get a fresh tenant and topic prefix, so runs never mix."""
    if request.param == "memory":
        return SEED, make_memory_adapters
    missing = missing_infra(REAL_PARTS)
    if missing:
        pytest.skip(f"infra not answering: {', '.join(missing)}")
    run_tag = uuid.uuid4().hex[:8]
    return {**SEED, "tenant_id": f"test_{run_tag}"}, real_adapters(REAL_PARTS, topic_prefix=f"e2e{run_tag}.")


@pytest.fixture
def run_all(setup):
    """Run every Lane A sample through one pipeline. Gives the lane, payments and each sample's correlation id."""
    seed, make_adapters = setup
    answers = {golden(key, "ProposedAction")["arguments"]["payment_ref"]: recorded_answer(key) for key in ("s2", "s3")}
    gateway, paid = fakes.make_fake_gateway()
    lane = orchestrate.build_lane(seed, fakes.make_model_by_ref(answers), gateway, NOW, make_adapters)
    correlations = {}
    for sample_id in LANE_A_SAMPLES:
        correlations[sample_id] = orchestrate.capture_signal(lane, RAW[sample_id]).correlation_id
        lane.bus.drain()
    yield lane, paid, correlations
    orchestrate.close_lane(lane)


def on_topic(lane, topic: str, correlation_id: str) -> list[dict]:
    """Payloads on one topic that belong to one sample."""
    return [env.payload for env in lane.bus.topics.get(topic, []) if env.correlation_id == correlation_id]


def end_of(lane, correlation_id: str) -> str:
    """Where a sample's journey stopped."""
    if on_topic(lane, "runs.completed", correlation_id):
        return "run_closed"
    if on_topic(lane, "tasks.unrouted", correlation_id):
        return "unrouted"
    return "duplicate_dropped"


def summarize(lane, paid: dict, correlation_id: str) -> dict:
    """What actually happened to one sample, in the same words as its expected block."""
    summary = {"end": end_of(lane, correlation_id)}
    runs = on_topic(lane, "runs.completed", correlation_id)
    if not runs:
        return summary
    approvals = on_topic(lane, "approvals.requested", correlation_id)
    refunds = [payment for key, payment in paid.items() if key.endswith(f":{runs[-1]['run_id']}:{ACTION_STEP_ID}")]
    summary.update(route="approval_required" if approvals else "execute", outcome=runs[-1]["outcome"], refunds=len(refunds))
    if refunds:
        summary["refund_amount_minor"] = refunds[0]["arguments"]["amount"]["amount_minor"]
    if approvals:
        human_step = next(step for step in runs[-1]["steps"] if step["kind"] == "human")
        summary.update(criticality=approvals[0]["criticality"], criticality_reasons=human_step["reason"].split(", "))
    return summary


def snapshot(lane) -> dict[str, list[dict]]:
    """Every payload on every topic, to compare two runs of the pipeline."""
    return {topic: [env.payload if hasattr(env, "payload") else env.model_dump() for env in envelopes] for topic, envelopes in lane.bus.topics.items()}


# --- The regression test

def test_every_sample_ends_as_expected(run_all):
    lane, paid, correlations = run_all
    for sample_id, correlation_id in correlations.items():
        assert summarize(lane, paid, correlation_id) == RAW[sample_id]["expected"], sample_id


def test_pipeline_totals_and_records(run_all):
    lane, paid, _ = run_all
    assert len(paid) == 1  # only s2 is paid; s3 waits, s4 is unrouted, s5 is a duplicate of s2
    assert (len(lane.bus.topics["approvals.requested"]), len(lane.bus.topics["tasks.unrouted"])) == (1, 1)
    assert not [topic for topic in lane.bus.topics if topic.endswith(".dlq")]
    assert len(lane.object_store) == 3  # s5 is a redelivery of s2, so it lands on the same raw object
    assert sorted(run["outcome"] for run in lane.records.list_kind("run")) == ["awaiting_approval", "resolved"]
    assert (len(lane.records.list_kind("approval")), len(lane.records.list_kind("action"))) == (1, 1)


def test_no_personal_data_on_any_topic(run_all):
    lane, _, _ = run_all
    personal = ["Nimal", "Dilani", "Kasun", "@example.lk", "+94", "199012345678"]
    published = str(snapshot(lane))  # raw bodies stay in the object store, never on a topic
    assert not [value for value in personal if value in published]
    assert "Dilani Fernando" in set(lane.vault.values())


def test_approving_s3_pays_once(run_all):
    lane, paid, _ = run_all
    approval_id = lane.bus.topics["approvals.requested"][0].payload["approval_id"]
    orchestrate.decide(lane, Decision(approval_id=approval_id, decision="approve", decided_by=["head_of_cs"], decided_at=NOW))
    lane.bus.drain()
    assert len(paid) == 2
    assert {run["run_id"]: run["outcome"] for run in lane.records.list_kind("run")} == {run["run_id"]: "resolved" for run in lane.records.list_kind("run")}


# --- Replay

def test_replaying_everything_changes_nothing(run_all):
    # Step 1: remember what happened
    lane, paid, _ = run_all
    before = snapshot(lane)

    # Step 2: Kafka redelivers every raw event, and every source sends its signal again
    for envelope in list(lane.bus.topics["signals.raw"]):
        lane.bus.redeliver("signals.raw", envelope)
    for sample_id in LANE_A_SAMPLES:
        orchestrate.capture_signal(lane, RAW[sample_id])
    lane.bus.drain()

    # Step 3: only the new raw captures appear; no new task, approval or payment
    after = snapshot(lane)
    assert {topic: items for topic, items in after.items() if topic != "signals.raw"} == {topic: items for topic, items in before.items() if topic != "signals.raw"}
    assert len(paid) == 1


def test_two_fresh_memory_runs_are_identical():
    """Memory only: on real infra, message timing can change the order ids are handed out."""
    def one_run():
        lane = orchestrate.build_lane(SEED, fakes.make_model_by_ref({golden("s2", "ProposedAction")["arguments"]["payment_ref"]: recorded_answer("s2")}), fakes.make_fake_gateway()[0], NOW)
        orchestrate.capture_signal(lane, RAW[LANE_A_SAMPLES[0]])
        lane.bus.drain()
        return snapshot(lane)

    assert one_run() == one_run()
