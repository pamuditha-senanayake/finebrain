# test_s4_orchestrate_bdd.py: S4 Orchestrate for the refund BDD, tested only at its boundary: K3 goes in, RunStarted comes out
# on runs.started. Lines: "the Planner agent reads the message and picks the refund recipe", "the Chat agent hands off to the
# Refund agent with the customer and chat attached". Then the contract, a golden RunStarted, rules that always hold, unhappy paths.
# Uses: stages_orchestrate.py, contracts_start.py, observe.py, tests/test_s1_refund_bdd.py (real S1 and S2 make Amara's K2).
import json
import random
from datetime import timedelta

import pytest

from app.pipeline import observe, stages_orchestrate
from app.pipeline.contracts_signal import TaskRequest, VersionRef
from app.pipeline.contracts_start import RunStarted
from tests.golden import NOW
from tests.test_s1_refund_bdd import CONFIRM, REFUND_ASK, poll, portal_message, shop as s1_shop

# Config
REFUND_SKILL = VersionRef(id="skill_refund_handling", version=3, branch="main", commit_id="cmt_0007")
FULL_PLAN = ["S5 Retrieve", "S6 Reason", "S7 Govern", "S8 Decide", "S9 Act", "S10 Record"]
shop = s1_shop  # "Given the shop website chat is connected", shared with S1


def amara_says(lane, inbox, *bodies: str) -> list[str]:
    """Amara's messages go through the real S1 and S2. Returns their K2 signal ids, oldest first."""
    inbox += [portal_message(len(inbox) + 1 + offset, body) for offset, body in enumerate(bodies)]  # inbox grows only after
    poll(lane)
    lane.bus.drain()  # S2 and S3 run; S3 sends the chat to tasks.unrouted today, so no S4 runs here
    return [signal["signal_id"] for signal in lane.records.list_kind("signal")]


def k3(signal_id: str, **overrides) -> TaskRequest:
    """K3 exactly as S3 should make it for Amara's refund ask."""
    task = {"task_id": f"task_{signal_id}", "signal_ids": [signal_id], "activity_id": "act_refund_request", "skill_ref": REFUND_SKILL,
            "agent_id": "agent_refund_worker", "on_behalf_of": None, "resolver_rule_id": "rr_refund_email", "match_score": 0.8,
            "base_criticality": 0, "due_at": NOW + timedelta(hours=4), "priority": 3}
    return TaskRequest.model_validate({**task, **overrides})


def start(lane, task: TaskRequest) -> RunStarted | None:
    """When S4 takes the task off tasks.created. The bus is not drained, so S5 onwards do not run."""
    return stages_orchestrate.begin_run(lane, lane.bus.publish("tasks.created", "task.created", task, "resolver"))


def published(lane, topic: str) -> list[dict]:
    return [envelope.payload for envelope in lane.bus.topics.get(topic, [])]


# --- BDD: the happy path

def test_the_planner_reads_amaras_message_and_picks_the_refund_recipe(shop):
    lane, inbox = shop
    [ask] = amara_says(lane, inbox, REFUND_ASK)
    started = start(lane, k3(ask))
    assert started.request_text == REFUND_ASK
    assert started.recipe.skill_ref == REFUND_SKILL and started.recipe.name == "Refund handling"
    assert started.recipe.allowed_tools == ["issue_refund", "reply_customer", "escalate"] and len(started.recipe.steps) == 4
    assert started.plan == FULL_PLAN


def test_the_chat_agent_hands_off_to_the_refund_agent_with_the_customer_and_chat(shop):
    lane, inbox = shop
    hello, ask, confirm = amara_says(lane, inbox, "Hi there", REFUND_ASK, CONFIRM)
    handoff = start(lane, k3(ask)).handoff
    assert (handoff.from_agent, handoff.to_agent) == ("agent_chat", "agent_refund_worker")
    assert handoff.customer_ref == "cust-amara" and handoff.thread_ref == "conn-shop-chat:c-1"
    assert handoff.transcript_signal_ids == [hello, ask]  # the chat so far, never a message after the task's own


# --- Contract: RunStarted is what S5 reads, and the seam log matches it

def test_run_started_matches_the_golden_master_and_continues_the_chain(shop):
    lane, inbox = shop
    [ask] = amara_says(lane, inbox, REFUND_ASK)
    started = start(lane, k3(ask))
    skill = lane.graph.at_version("skill", "skill_refund_handling", 3)
    assert published(lane, "runs.started") == [{
        "run_id": started.run_id, "task_id": f"task_{ask}", "signal_id": ask, "agent_id": "agent_refund_worker",
        "request_text": REFUND_ASK, "plan": FULL_PLAN,
        "recipe": {"skill_ref": REFUND_SKILL.model_dump(), "name": "Refund handling", "allowed_tools": skill["allowed_tools"], "steps": skill["steps"]},
        "handoff": {"handoff_id": f"{started.run_id}:handoff", "from_agent": "agent_chat", "to_agent": "agent_refund_worker",
                    "customer_ref": "cust-amara", "thread_ref": "conn-shop-chat:c-1", "transcript_signal_ids": [ask]},
    }]
    task_envelope, started_envelope = lane.bus.topics["tasks.created"][-1], lane.bus.topics["runs.started"][-1]  # and it continues the chain
    assert started_envelope.correlation_id == task_envelope.correlation_id and started_envelope.causation_id == task_envelope.event_id


def test_the_seam_log_records_what_came_in_and_went_out(shop, tmp_path, monkeypatch):
    lane, inbox = shop
    monkeypatch.setattr(observe, "SEAM_LOG_DIR", str(tmp_path))
    [ask] = amara_says(lane, inbox, REFUND_ASK)
    started = start(lane, k3(ask))
    line = json.loads((tmp_path / "S4.jsonl").read_text().splitlines()[0])
    assert TaskRequest.model_validate(line["in"]) == k3(ask) and RunStarted.model_validate(line["out"]) == started


# --- Rules that always hold, over many random chats and tasks

@pytest.mark.parametrize("seed", range(30))
def test_rules_hold_for_any_chat(shop, seed):
    lane, inbox = shop
    picker = random.Random(seed)
    signal_ids = amara_says(lane, inbox, *[picker.choice([REFUND_ASK, CONFIRM, "ok", "é ✓"]) for _ in range(picker.randint(1, 8))])
    picked = [picker.choice(signal_ids) for _ in range(picker.randint(1, 4))]
    for signal_id in picked:
        start(lane, k3(signal_id))
    runs, joins = [RunStarted.model_validate(payload) for payload in published(lane, "runs.started")], published(lane, "runs.continued")
    # One chat and nothing closed: the first task starts the run, every other distinct task joins it, each exactly once
    assert len(runs) == 1 and {join["run_id"] for join in joins} <= {runs[0].run_id}
    assert sorted([runs[0].task_id] + [join["task_id"] for join in joins]) == sorted({f"task_{signal_id}" for signal_id in picked})
    assert runs[0].handoff.transcript_signal_ids == signal_ids[: signal_ids.index(runs[0].signal_id) + 1]
    assert all(run.plan == FULL_PLAN for run in runs)


# --- Unhappy paths: S4 starts nothing and a human is told, through an escalated run

@pytest.mark.parametrize("change, reason", [
    ({"skill_ref": REFUND_SKILL.model_copy(update={"version": 99})}, "recipe_missing"),
    ({"agent_id": "agent_nobody"}, "agent_unknown"),
    ({"signal_ids": ["sig_never_seen"]}, "signal_missing"),
])
def test_a_task_s4_cannot_start_is_escalated(shop, change, reason):
    lane, inbox = shop
    [ask] = amara_says(lane, inbox, REFUND_ASK)
    assert start(lane, k3(ask, **change)) is None
    assert "runs.started" not in lane.bus.topics
    [record] = published(lane, "runs.completed")
    assert record["outcome"] == "escalated" and record["steps"][0]["decision"] == reason


def test_the_same_task_twice_starts_one_run(shop):
    lane, inbox = shop
    [ask] = amara_says(lane, inbox, REFUND_ASK)
    first = start(lane, k3(ask))
    assert start(lane, k3(ask)) is None
    assert [run["run_id"] for run in published(lane, "runs.started")] == [first.run_id]


def test_a_message_that_is_not_a_chat_has_no_handoff(shop):
    lane, inbox = shop
    [ask] = amara_says(lane, inbox, REFUND_ASK)
    lane.records.save("signal", ask, lane.signals[ask].model_copy(update={"thread_ref": None, "channel": "email"}))
    lane.signals.pop(ask)
    assert start(lane, k3(ask)).handoff is None


def test_a_records_outage_still_starts_the_run_with_this_message_alone(shop):
    lane, inbox = shop
    _, ask = amara_says(lane, inbox, "Hi there", REFUND_ASK)
    lane.records.save = lane.records.load = lane.records.list_kind = lambda *args: (_ for _ in ()).throw(ConnectionError("database down"))
    assert start(lane, k3(ask)).handoff.transcript_signal_ids == [ask]  # lane.signals still holds her message
