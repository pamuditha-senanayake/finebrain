# test_activity_real.py: the Landing page chat activity for real. Built through Workflow Studio's API on Postgres, Valkey,
# Redpanda and S3, read back from the Postgres graph; a visitor's message on the live portal connection runs S1 to S10, and
# the owner's reply lands in the real portal conversation, read back from the portal. Skips when infra or the portal is missing.
# Uses: tests/activity_world.py, tests/test_s9_chat_real.py (portal key and Amara's conversation), adapters.py, kafka_admin.py.
import uuid

import pytest

from app.pipeline import conn_call
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.kafka_admin import delete_prefixed_topics
from tests.activity_world import LANDING, STATEMENT, WF, answer_with, build, build_landing, node, visitor
from tests.s6_world import scripted
from tests.s7_world import runs
from tests.test_s1_real import read_topic
from tests.test_s5_real import S5_PARTS, parts
from tests.test_s9_chat_real import AMARA_CHAT, portal_is_up, portal_key

pytestmark = [pytest.mark.skipif(bool(missing_infra(S5_PARTS)), reason="infra not answering"),
              pytest.mark.skipif(not portal_is_up(), reason="no portal key, or the portal is not answering")]


def in_her_chat(lane, text: str) -> list[dict]:
    messages = conn_call.call(lane, conn_call.load(lane, LANDING), "conversation", {"conversation_id": AMARA_CHAT})["messages"]
    return [m for m in messages if m["sender"] != "customer" and m["body"] == text]


@pytest.fixture
def real():
    tag = uuid.uuid4().hex[:8]
    client, lane = build(real_adapters(parts(), topic_prefix=f"act{tag}."), tenant=f"test_act_{tag}", key=portal_key())
    yield client, lane, tag
    delete_prefixed_topics(f"act{tag}.")


def test_studio_writes_the_activity_and_its_rule_to_the_postgres_graph(real):
    client, lane, _ = real
    ids = build_landing(client, lane)
    activity, rule = node(lane, "workflow", WF), node(lane, "resolver_rule", f"rr_landing_page_chat_{LANDING}")  # read from Postgres
    assert (activity["owner"], activity["skill_id"], activity["policies"], activity["connections"]) == (ids["agent"], ids["skill"], [ids["policy"]], [LANDING])
    assert (rule["connectors"], rule["paused"]) == ([LANDING], False)
    assert node(lane, "knowledge", f"{ids['policy']}_statement")["text"] == STATEMENT


def test_a_visitors_two_messages_are_answered_in_the_real_portal_chat(real):
    client, lane, tag = real
    ids = build_landing(client, lane)
    ask, close = f"[brain test {tag}] Which product would you like to see in the demo?", f"[brain test {tag}] Thanks. A person will book your demo today."
    lane.model, calls = scripted(answer_with(ids["policy"], ask, waits=True), answer_with(ids["policy"], close))
    visitor(lane, "Can I see a demo?", conversation=AMARA_CHAT)
    visitor(lane, "The Agent Gateway please", conversation=AMARA_CHAT)
    executed = [m["payload"] for m in read_topic(f"act{tag}.actions.executed", 2)]  # from Redpanda
    assert [(a["tool_id"], a["status"]) for a in executed] == [("tool_reply_email", "succeeded")] * 2
    assert [m["id"] for m in in_her_chat(lane, ask)] == [executed[0]["external_ref"]] and [m["id"] for m in in_her_chat(lane, close)] == [executed[1]["external_ref"]]
    assert STATEMENT in str(calls[0]["messages"]) and list(runs(lane).values()) == [["awaiting_customer", "resolved"]]
    assert lane.records.load("run", executed[1]["run_id"])["outcome"] == "resolved"  # from Postgres
