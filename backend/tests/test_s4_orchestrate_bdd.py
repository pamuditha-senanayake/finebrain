# test_s4_orchestrate_bdd.py: S4 Orchestrate on its own, for the refund BDD (website chat). Anna's message runs through the
# real S1, S2 and S3; S4's consumer is left off, so each test hands S3's real task to S4 and nothing after S4 runs.
# Lines: "the Planner agent reads the message and picks the refund recipe", "the Chat agent hands off to the Refund agent
# with the customer and chat attached". Then the contract, a golden RunStarted, the agent as Studio saved it, unhappy paths.
# Uses: stages_orchestrate.py, contracts_start.py, observe.py, store_graph.py, tests/test_s1_refund_chat.py (Anna's webhook).
import json

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate, stages_orchestrate
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.contracts_start import RunStarted
from app.pipeline.store_graph import CLOSED
from tests.golden import NOW, SEED
from tests.test_s1_refund_chat import FIRST, SESSION, send

# Config
REFUND_SKILL = {"id": "skill_refund_handling", "version": 3, "branch": "main", "commit_id": "cmt_0007"}
FULL_PLAN = ["S5 Retrieve", "S6 Reason", "S7 Govern", "S8 Decide", "S9 Act", "S10 Record"]
ANNA = "pii_tok_31c9b7d630f8651eb93bf8"  # her token from S2, frozen in tests/test_s2_checks.py
HELLO = {"id": "chat_msg_anna_0", "text": "Hi there"}


# --- Helpers

@pytest.fixture
def lane():
    """S1, S2 and S3 run for real; S4's consumer is off, so the test hands each task to S4 itself."""
    observe.reset_counts()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    lane.bus.subscribers.pop("tasks.created")
    return lane


def anna_says(lane, *messages: dict) -> None:
    """Each message posted by the chat webhook, then S1, S2 and S3 catch up."""
    client = TestClient(capture_api.create_app(lane))
    for message in messages:
        assert send(client, message).status_code == 202
        lane.bus.drain()


def tasks(lane) -> list:
    return lane.bus.topics.get("tasks.created", [])


def start(lane, envelope) -> RunStarted | None:
    return stages_orchestrate.begin_run(lane, envelope)


def hand_made(lane, **change):
    """S3's real task with one field changed, published like S3 would."""
    task = TaskRequest.model_validate({**tasks(lane)[0].payload, "task_id": "task_changed", **change})
    return lane.bus.publish("tasks.created", "task.created", task, "resolver")


def published(lane, topic: str) -> list[dict]:
    return [envelope.payload for envelope in lane.bus.topics.get(topic, [])]


def save_agent(lane, **body) -> None:
    """Workflow Studio saves the refund agent as a new version in the graph."""
    current = next(node for node in lane.graph.latest("agent") if node["_ref"]["id"] == "agent_refund_worker")
    fields = {key: value for key, value in current.items() if key != "_ref"}
    lane.graph.put("agent", "agent_refund_worker", current["_ref"]["version"] + 1, "studio", {**fields, **body})


# --- BDD: the happy path

def test_the_planner_reads_annas_message_and_picks_the_refund_recipe(lane):
    anna_says(lane, FIRST)
    started = start(lane, tasks(lane)[0])
    assert started.request_text == FIRST["text"]
    assert started.recipe.skill_ref.model_dump() == REFUND_SKILL and started.recipe.name == "Refund handling"
    assert started.recipe.allowed_tools == ["issue_refund", "reply_customer", "escalate"] and len(started.recipe.steps) == 4
    assert started.plan == FULL_PLAN


def test_the_chat_agent_hands_off_to_the_refund_agent_with_the_customer_and_chat(lane):
    anna_says(lane, HELLO, FIRST)  # "Hi there" matches no rule, so only her refund request becomes a task
    [task] = tasks(lane)
    handoff = start(lane, task).handoff
    assert (handoff.from_agent, handoff.to_agent) == ("agent_chat", "agent_refund_worker")
    assert (handoff.customer_ref, handoff.conversation_id) == (ANNA, SESSION)
    assert handoff.transcript_signal_ids == ["sig_0001", "sig_0002"]  # the whole chat so far, greeting included


# --- Contract: RunStarted is what S5 reads, and the seam log matches it

def test_run_started_matches_the_golden_master_and_continues_the_chain(lane):
    anna_says(lane, FIRST)
    start(lane, tasks(lane)[0])
    assert published(lane, "runs.started") == [{  # reviewed by hand once, then frozen
        "run_id": "run_0001", "task_id": "task_0001", "signal_id": "sig_0001", "agent_id": "agent_refund_worker",
        "request_text": FIRST["text"], "plan": FULL_PLAN,
        "recipe": {"skill_ref": REFUND_SKILL, "name": "Refund handling", "allowed_tools": ["issue_refund", "reply_customer", "escalate"],
                   "steps": lane.graph.at_version("skill", "skill_refund_handling", 3)["steps"]},
        "handoff": {"handoff_id": "run_0001:handoff", "from_agent": "agent_chat", "to_agent": "agent_refund_worker",
                    "customer_ref": ANNA, "conversation_id": SESSION, "transcript_signal_ids": ["sig_0001"]},
    }]
    task_envelope, started_envelope = tasks(lane)[0], lane.bus.topics["runs.started"][0]
    assert started_envelope.correlation_id == task_envelope.correlation_id and started_envelope.causation_id == task_envelope.event_id


def test_the_seam_log_records_what_came_in_and_went_out(lane, tmp_path, monkeypatch):
    monkeypatch.setattr(observe, "SEAM_LOG_DIR", str(tmp_path))
    anna_says(lane, FIRST)
    started = start(lane, tasks(lane)[0])
    line = json.loads((tmp_path / "S4.jsonl").read_text().splitlines()[0])
    assert TaskRequest.model_validate(line["in"]).model_dump(mode="json") == tasks(lane)[0].payload
    assert RunStarted.model_validate(line["out"]) == started and "I want" not in json.dumps(line["in"])  # the task holds no message text


# --- The agent is read from the graph, as Workflow Studio last saved it

def test_an_agent_studio_removed_is_refused(lane):
    anna_says(lane, FIRST)
    save_agent(lane, **{CLOSED: True})
    assert start(lane, tasks(lane)[0]) is None
    assert published(lane, "runs.completed")[0]["steps"][0]["decision"] == "agent_unknown"


def test_rights_studio_changed_are_what_the_run_gets(lane):
    save_agent(lane, capabilities=["kb.read"])
    assert stages_orchestrate.principal_of(lane, "agent_refund_worker").capabilities == ["kb.read"]  # S5 and S7 act on this


# --- Unhappy paths: S4 starts nothing and a human is told, through an escalated run

@pytest.mark.parametrize("change, reason", [
    ({"skill_ref": {**REFUND_SKILL, "version": 99}}, "recipe_missing"),
    ({"agent_id": "agent_nobody"}, "agent_unknown"),
    ({"signal_ids": ["sig_never_seen"]}, "signal_missing"),
])
def test_a_task_s4_cannot_start_is_escalated(lane, change, reason):
    anna_says(lane, FIRST)
    assert start(lane, hand_made(lane, **change)) is None
    assert "runs.started" not in lane.bus.topics
    [record] = published(lane, "runs.completed")
    assert record["outcome"] == "escalated" and record["steps"][0]["decision"] == reason


def test_the_same_task_twice_starts_one_run(lane):
    anna_says(lane, FIRST)
    start(lane, tasks(lane)[0])
    assert start(lane, tasks(lane)[0]) is None and len(published(lane, "runs.started")) == 1


def test_a_crash_mid_start_frees_the_task_for_a_redelivery(lane, monkeypatch):
    anna_says(lane, FIRST)
    publish = lane.bus.publish
    monkeypatch.setattr(lane.bus, "publish", lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("broker down")))
    with pytest.raises(ConnectionError):
        start(lane, tasks(lane)[0])
    monkeypatch.setattr(lane.bus, "publish", publish)
    assert start(lane, tasks(lane)[0]).run_id  # the claims were released, so the redelivery starts the run


def test_a_message_that_is_not_a_chat_has_no_handoff(lane):
    anna_says(lane, FIRST)
    signal = lane.signals["sig_0001"]
    lane.signals["sig_0001"] = signal.model_copy(update={"conversation_id": None, "channel": "email"})
    assert start(lane, tasks(lane)[0]).handoff is None


def test_a_records_outage_still_starts_the_run_with_this_message_alone(lane):
    anna_says(lane, HELLO, FIRST)
    down = lambda *args: (_ for _ in ()).throw(ConnectionError("database down"))  # noqa: E731
    lane.records.save = lane.records.load = lane.records.history = down
    assert start(lane, tasks(lane)[0]).handoff.transcript_signal_ids == ["sig_0002"]
