# test_s6_real.py: S1 to S6 on real infra with real Claude. Anna's two visits run through SeaweedFS, Postgres (vault,
# graph, knowledge, records), Valkey and Redpanda; S5 reads her orders from the shop's own database; S6 asks first, then
# refunds exactly her latest order. The turns are read back from Postgres and the access decisions from Redpanda.
# Uses: run_steps.py, adapters.py, kafka_admin.py, tests/s5_world.py, tests/s6_world.py, tests/test_s5_real.py, tests/test_s1_real.py.
import uuid

import pytest

from app.pipeline import run_steps
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.s5_world import make_lane, world_seed
from tests.s6_world import MOUSE, real_claude, visit_1, visit_2
from tests.test_s1_real import read_topic
from tests.test_s5_real import S5_PARTS, parts


@pytest.fixture
def real():
    missing = missing_infra(S5_PARTS)
    if missing:
        pytest.skip(f"infra not answering: {', '.join(missing)}")
    tag = uuid.uuid4().hex[:8]
    lane = make_lane(real_adapters(parts(), topic_prefix=f"s6{tag}."), seed={**world_seed(), "tenant_id": f"test_{tag}"})
    lane.bus.subscribers = {topic: lane.bus.subscribers[topic][:1] for topic in ("signals.raw", "signals.normalized")}
    lane.model = real_claude()
    yield lane, tag
    for uri in list(lane.object_store):
        del lane.object_store[uri]
    delete_prefixed_topics(f"s6{tag}.")


def test_annas_two_visits_ask_then_refund_on_real_infra(real):
    lane, tag = real
    started, _, first = visit_1(lane)
    _, _, second = visit_2(lane)
    assert first.action_type == "reply_customer" and first.arguments["awaits_customer"] is True, first.rationale_summary
    assert second.action_type == "issue_refund" and (second.arguments["payment_ref"], second.money.amount_minor) == (MOUSE["payment_ref"], 400000)
    turns = run_steps.previous_turns(lane, started.run_id)  # read back from Postgres
    assert [turn["action_type"] for turn in turns] == ["reply_customer", "issue_refund"]
    decisions = [m["payload"] for m in read_topic(f"s6{tag}.access.decisions", 2)]  # one S5 read per visit, on Redpanda
    assert len(decisions) == 2 and all("2 orders" in d["reason"] for d in decisions)
