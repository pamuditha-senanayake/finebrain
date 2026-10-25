# test_s3_refund_chat.py: S3 for the refund happy path BDD (website chat). S3 is reached once, by Anna's refund request.
# Proves the Planner picks the refund recipe and hands on a complete workflow: rule, pinned skill with its steps, agent.
# Uses: capture_api.py, orchestrate.py, stages_route.py, contracts_signal.py, tests/test_s1_refund_chat.py, tests/test_s2_checks.py.
import json
import logging
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate
from app.pipeline.contracts_signal import TaskRequest
from tests.golden import NOW, SEED
from tests.test_s1_refund_chat import FIRST, send
from tests.test_s2_checks import FROZEN as S2_FROZEN

# Config
REFUND_SKILL = {"id": "skill_refund_handling", "version": 3, "branch": "main", "commit_id": "cmt_0007"}


# --- Helpers

@pytest.fixture
def lane():
    """S1, S2 and S3 only, so S3's output can be checked before S4 picks it up."""
    observe.reset_counts()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    lane.bus.subscribers = {topic: lane.bus.subscribers[topic][:1] for topic in ("signals.raw", "signals.normalized")}
    return lane


def anna_asks_for_a_refund(lane) -> None:
    """Given the chat is connected, when Anna types her refund request, the message runs through S1, S2 and S3."""
    assert send(TestClient(capture_api.create_app(lane)), FIRST).status_code == 202
    lane.bus.drain()


def payloads(lane, topic: str) -> list[dict]:
    return [envelope.payload for envelope in lane.bus.topics.get(topic, [])]


# --- 1. What S3 receives

def test_s3_receives_annas_masked_signal_from_s2(lane):
    anna_asks_for_a_refund(lane)
    [received] = payloads(lane, "signals.normalized")
    assert {key: value for key, value in received.items() if key not in ("signal_id", "raw_event_id")} == S2_FROZEN[0]


# --- 2. The Planner picks the refund recipe

def test_planner_picks_the_refund_recipe(lane):
    anna_asks_for_a_refund(lane)
    [task] = payloads(lane, "tasks.created")
    assert (task["resolver_rule_id"], task["activity_id"], task["agent_id"]) == ("rr_refund_chat", "act_refund_request", "agent_refund_worker")
    assert payloads(lane, "tasks.unrouted") == [] and observe.read_count("s3.routed") == 1


def test_planner_assembles_the_workflow_from_the_library(lane):
    """The task names a released skill version; reading it back gives the steps, tools and agent the workflow runs with."""
    anna_asks_for_a_refund(lane)
    task = TaskRequest.model_validate(payloads(lane, "tasks.created")[0])
    skill = next(node for node in lane.graph.latest("skill") if node["_ref"]["id"] == task.skill_ref.id)
    agent = next(node for node in lane.graph.latest("agent") if node["_ref"]["id"] == task.agent_id)
    assert task.skill_ref.model_dump() == REFUND_SKILL
    assert "issue_refund" in skill["allowed_tools"] and len(skill["steps"]) == 4
    assert "refund.propose" in agent["capabilities"]


# --- 3. What S3 hands on

def test_s3_hands_on_one_complete_task(lane):
    anna_asks_for_a_refund(lane)
    [signal], [task] = payloads(lane, "signals.normalized"), payloads(lane, "tasks.created")
    assert task["signal_ids"] == [signal["signal_id"]]
    assert task["due_at"] == (NOW + timedelta(hours=4)).isoformat() and task["priority"] == 3
    assert task["flags"] == [] and task["on_behalf_of"] is None
    assert lane.bus.topics["tasks.created"][0].correlation_id == lane.bus.topics["signals.raw"][0].correlation_id  # one journey


# --- State S3 leaves behind: the signal kept for other workers, one task, nothing unrouted

def test_s3_keeps_the_signal_and_creates_exactly_one_task(lane):
    anna_asks_for_a_refund(lane)
    [signal] = payloads(lane, "signals.normalized")
    assert list(lane.signals) == [signal["signal_id"]]
    assert lane.records.load("signal", signal["signal_id"])["conversation_id"] == "chat_sess_anna"
    assert (len(payloads(lane, "tasks.created")), len(payloads(lane, "tasks.unrouted"))) == (1, 0)


# --- Seam logs: what came in from S2 and what went out to S4, no personal data

def test_seam_logs_match_k2_and_k3(lane, caplog):
    with caplog.at_level(logging.INFO, logger=observe.LOGGER_NAME):
        anna_asks_for_a_refund(lane)
    lines = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    seam_in = next(line for line in lines if line["stage"] == "S3" and line["event"] == "seam_in")
    seam_out = next(line for line in lines if line["stage"] == "S3" and line["event"] == "seam_out")
    [signal], [task] = payloads(lane, "signals.normalized"), payloads(lane, "tasks.created")
    assert (seam_in["signal_id"], seam_in["conversation_id"]) == (signal["signal_id"], signal["conversation_id"])
    assert {key: seam_out[key] for key in ("task_id", "signal_ids", "resolver_rule_id", "skill_ref", "agent_id", "flags")} == {
        key: task[key] for key in ("task_id", "signal_ids", "resolver_rule_id", "skill_ref", "agent_id", "flags")}
    assert "Anna" not in caplog.text and "anna@example.lk" not in caplog.text
