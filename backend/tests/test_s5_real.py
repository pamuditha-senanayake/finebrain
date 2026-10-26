# test_s5_real.py: S1 to S5 on real infra. Anna's message is captured to SeaweedFS, masked into the Postgres vault, routed
# from the Postgres graph over Redpanda, started by S4 with Valkey claims, and S5 searches the Postgres knowledge (with
# real Voyage when its key is set) and reads her orders from the shop's own database. The access decision is read back
# from Redpanda. Skips when the services are not answering. Uses: orchestrate.py, run_steps.py, retrieve_case.py,
# adapters.py, kafka_admin.py, tests/s5_world.py, tests/test_s1_real.py, scripts/test_keys.py.
import os
import uuid

import pytest

from app.pipeline import embeddings, run_steps, stages_orchestrate
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.kafka_admin import delete_prefixed_topics
from scripts.test_keys import ENV_PATH, load_env_file
from tests.s5_world import make_lane, visitor_says, world_seed
from tests.test_s1_real import read_topic
from tests.test_s1_refund_chat import FIRST, SECOND

# Config
S5_PARTS = frozenset({"s3", "postgres", "valkey", "kafka", "opa"})


def parts() -> frozenset[str]:
    """The real parts, with Voyage when its key is set (it costs a little per call). embeddings.py reads its address and
    models when imported, so they are applied after .env loads, as main.py does by loading .env before any import."""
    load_env_file(ENV_PATH)
    embeddings.VOYAGE_BASE_URL = os.environ.get("VOYAGE_BASE_URL", embeddings.VOYAGE_BASE_URL)
    embeddings.EMBED_MODEL = os.environ.get("VOYAGE_MODEL", embeddings.EMBED_MODEL)
    embeddings.RERANK_MODEL = os.environ.get("VOYAGE_RERANK_MODEL", embeddings.RERANK_MODEL)
    return S5_PARTS | ({"voyage"} if not missing_infra(frozenset({"voyage"})) else set())


@pytest.fixture
def real():
    missing = missing_infra(S5_PARTS)
    if missing:
        pytest.skip(f"infra not answering: {', '.join(missing)}")
    tag = uuid.uuid4().hex[:8]
    lane = make_lane(real_adapters(parts(), topic_prefix=f"s5{tag}."), seed={**world_seed(), "tenant_id": f"test_{tag}"})
    lane.bus.subscribers = {topic: lane.bus.subscribers[topic][:1] for topic in ("signals.raw", "signals.normalized")}
    bundles = []

    def s4_then_s5(envelope) -> None:
        """S4 starts the run (or joins it), then the run asks S5, as run_steps.start_run does before S6."""
        started = stages_orchestrate.begin_run(lane, envelope)
        if started:
            task = TaskRequest.model_validate(envelope.payload)
            query = run_steps.query_for(lane, task, run_steps.signal_of(lane, task.signal_ids[0]), stages_orchestrate.principal_of(lane, task.agent_id), started.run_id)
            bundles.append(run_steps.retrieve_with_retry(lane, query, envelope))

    lane.bus.subscribe("tasks.created", "worker", "S4", s4_then_s5)
    yield lane, tag, bundles
    for uri in list(lane.object_store):
        del lane.object_store[uri]
    delete_prefixed_topics(f"s5{tag}.")


def test_annas_refund_runs_s1_to_s5_on_real_infra(real):
    lane, tag, bundles = real
    visitor_says(lane, FIRST)
    [bundle] = bundles
    shown = {item.item_id for item in bundle.items}
    assert {"item_policy_window", "item_policy_auto_limit", "order:ORD-1002", "order:ORD-1001"} <= shown  # Postgres knowledge and the shop's database
    assert "item_fraud_watch" not in shown and bundle.denied_count == 1
    [decision] = [m["payload"] for m in read_topic(f"s5{tag}.access.decisions", 1)]  # the audit trail, read back from Redpanda
    assert decision["decision"] == "allow" and "2 orders" in decision["reason"] and decision["run_id"] == lane.bus.topics["runs.started"][0].payload["run_id"]


def test_visit_2_joins_the_run_and_does_not_start_a_second_retrieval(real):
    lane, tag, bundles = real
    visitor_says(lane, FIRST)
    visitor_says(lane, SECOND)
    assert len(bundles) == 1 and len(read_topic(f"s5{tag}.runs.continued", 1)) == 1  # the run goes on; S6 reads the joined message
