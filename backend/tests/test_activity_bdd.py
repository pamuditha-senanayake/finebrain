# test_activity_bdd.py: a workflow is an activity. Built in Workflow Studio, it lands in the graph with its owner, its one
# skill, its policies and its connections, plus a routing rule per connection; S3 then sends every message on that
# connection to it, S4 hands it to the owner, S5 gives the owner its policies by key, and the reply goes back into the
# visitor's chat. Every visit of the chat, a draft that routes nothing, a sensor on no real connection, and taking a right
# away. Uses: tests/activity_world.py, stages_route.py, api/studio_state.py, api/studio_findings.py, api/studio_chat_context.py.
from app.api.studio_chat_context import context_of
from app.api.studio_findings import health
from app.api.studio_state import Studio
from types import SimpleNamespace

from app.pipeline import conn_call, run_finish, stages_govern, stages_route
from app.pipeline.contracts_signal import Signal
from tests.activity_world import LANDING, STATEMENT, WF, answer_with, apply, build, build_landing, node, stand_in_portal, visitor
from tests.golden import golden
from tests.s6_world import scripted
from tests.s7_world import runs

# Config
RULE = f"rr_landing_page_chat_{LANDING}"


def tasks(lane) -> list[dict]:
    return [e.payload for e in lane.bus.topics.get("tasks.created", [])]


# --- Studio puts the activity in the graph

def test_studio_puts_the_activity_its_owner_skill_policy_and_rule_in_the_graph():
    client, lane = build()
    ids = build_landing(client, lane)
    activity = node(lane, "workflow", WF)
    assert {k: activity[k] for k in ("activity_id", "owner", "skill_id", "policies", "connections")} == {
        "activity_id": "landing_page_chat", "owner": ids["agent"], "skill_id": ids["skill"], "policies": [ids["policy"]], "connections": [LANDING]}
    rule = node(lane, "resolver_rule", RULE)
    assert (rule["connectors"], rule["channels"], rule["paused"], rule["activity_id"]) == ([LANDING], ["chat"], False, "landing_page_chat")
    assert node(lane, "knowledge", f"{ids['policy']}_statement")["text"] == STATEMENT  # a new policy's wording, for S5 and S6
    assert node(lane, "agent", ids["agent"])["capabilities"] == ["kb.read", "reply.draft"]


def test_a_draft_activity_routes_nothing(monkeypatch):
    client, lane = build()
    stand_in_portal(monkeypatch)
    build_landing(client, lane, live=False)
    assert node(lane, "resolver_rule", RULE)["paused"] is True
    visitor(lane, "Can I see a demo?")
    assert not any(t["activity_id"] == "landing_page_chat" for t in tasks(lane))


# --- A visitor's chat, every visit

def test_a_visitor_is_answered_by_the_owner_with_its_policy_in_hand(monkeypatch):
    client, lane = build()
    posted = stand_in_portal(monkeypatch)
    ids = build_landing(client, lane)
    lane.model, calls = scripted(answer_with(ids["policy"]))
    visitor(lane, "How much is the Agent Gateway? Any discount?")
    task = tasks(lane)[-1]
    assert (task["activity_id"], task["agent_id"], task["skill_ref"]["id"]) == ("landing_page_chat", ids["agent"], ids["skill"])
    assert STATEMENT in str(calls[0]["messages"])  # S5 gave the owner its policy by key
    assert [(p["conversationId"], p["body"]) for p in posted] == [("c-landing-1", answer_with(ids["policy"])["tool_input"]["message_plain"])]
    assert list(runs(lane).values()) == [["resolved"]]


def test_a_follow_up_in_the_same_chat_joins_the_open_run(monkeypatch):
    client, lane = build()
    posted = stand_in_portal(monkeypatch)
    ids = build_landing(client, lane)
    lane.model, _ = scripted(answer_with(ids["policy"], "Which product would you like to see?", waits=True), answer_with(ids["policy"], "Thanks, a person will book your demo."))
    visitor(lane, "Can I see a demo?")
    visitor(lane, "The Agent Gateway please")
    assert len(posted) == 2 and list(runs(lane).values()) == [["awaiting_customer", "resolved"]]  # one run, two turns


def test_a_refund_word_on_the_landing_chat_still_goes_to_its_own_activity(monkeypatch):
    client, lane = build()
    stand_in_portal(monkeypatch)
    ids = build_landing(client, lane)
    lane.model, _ = scripted(answer_with(ids["policy"]))
    visitor(lane, "I want a refund for my payment")
    assert tasks(lane)[-1]["activity_id"] == "landing_page_chat"


def test_other_connections_keep_their_keyword_rules():
    client, lane = build()
    build_landing(client, lane)
    signal = Signal.model_validate(golden("s2", "Signal")).model_copy(update={"connector_id": "conn_gmail_support"})  # Nimal's refund email
    task, _ = stages_route.route(signal, stages_route.read_routing(lane.graph), None, lane.now)
    assert task.activity_id == "act_refund_request"


# --- What Studio must refuse or flag

def test_a_sensor_on_no_real_connection_is_flagged_and_gets_no_rule():
    client, lane = build()
    build_landing(client, lane, source="Landing chat")  # a name, not a connection id
    st = Studio.of(lane)
    assert any("not a connection" in f["text"] for f in health(st, st.flows[WF])["findings"])
    assert node(lane, "resolver_rule", RULE) is None and node(lane, "workflow", WF)["connections"] == []


def test_removing_the_sensor_closes_its_rule():
    client, lane = build()
    ids = build_landing(client, lane)
    apply(client, lane, "sensor", {}, intent="delete", target=ids["sensor"])
    assert node(lane, "resolver_rule", RULE) is None


def test_taking_reply_draft_away_in_studio_stops_the_replies(monkeypatch):
    client, lane = build()
    posted = stand_in_portal(monkeypatch)
    ids = build_landing(client, lane)
    apply(client, lane, "agent", {"fields": {"capabilities": ["kb.read"]}}, intent="update", target=ids["agent"])
    lane.model, _ = scripted(answer_with(ids["policy"]))
    visitor(lane, "What does the Agent Gateway do?")
    assert [p["body"] for p in posted] == [run_finish.HANDOFF_TEXT]  # no answer goes out, only the notice that a person will reply
    assert list(runs(lane).values())[-1] == ["blocked"]  # S7 read the agent's rights from the graph


def test_the_studio_assistant_knows_the_connections():
    client, lane = build()
    build_landing(client, lane, live=False)
    st = Studio.of(lane)
    assert '"id": "conn_landing_chat"' in context_of(lane, st, st.flows[WF], "h-pamuditha", None, None)


# --- Nobody waits in silence

def escalate(policy_id: str) -> dict:
    return {"tool": "escalate", "tool_input": {"reason": "Pricing goes to a person.", "rationale_summary": "The policy says pricing goes to a person.",
                                               "citations": [f"{policy_id}_statement"], "confidence": 0.9}}


def test_an_escalation_tells_the_visitor_a_person_will_reply_once(monkeypatch):
    client, lane = build()
    posted = stand_in_portal(monkeypatch)
    ids = build_landing(client, lane)
    lane.model, _ = scripted(escalate(ids["policy"]))
    visitor(lane, "Can I get a 20% discount?")
    assert [p["body"] for p in posted] == [run_finish.HANDOFF_TEXT]
    signal_id = tasks(lane)[-1]["signal_ids"][0]
    run = SimpleNamespace(task=SimpleNamespace(signal_ids=[signal_id]), action=SimpleNamespace(run_id=lane.bus.topics["runs.completed"][-1].payload["run_id"], step_id="step_04"))
    run_finish.tell_customer(lane, run, "handoff_message", run_finish.HANDOFF_TEXT, "handoff")  # a replay of the same close
    assert len(posted) == 1


def test_a_run_waiting_for_approval_tells_the_visitor_and_a_failed_notice_never_stops_the_record(monkeypatch):
    client, lane = build()
    posted = stand_in_portal(monkeypatch)
    ids = build_landing(client, lane)
    lane.model, _ = scripted(answer_with(ids["policy"]), answer_with(ids["policy"]))
    monkeypatch.setattr(stages_govern, "decide_criticality", lambda *args: (2, ["a person approves replies here"]))  # as a stricter tenant sets it
    visitor(lane, "Can I see a demo?")
    assert [p["body"] for p in posted] == [run_finish.WAITING_TEXT] and list(runs(lane).values()) == [["awaiting_approval"]]
    monkeypatch.setattr(conn_call, "http", None)  # the chat is unreachable now
    visitor(lane, "Hello again?", conversation="c-landing-2")
    assert list(runs(lane).values())[-1] == ["awaiting_approval"]  # recorded all the same


def test_the_connections_list_says_which_ones_a_sensor_can_listen_to():
    client, lane = build()
    listed = client.get(f"/api/t/{lane.seed['tenant_id']}/connections", headers={"x-persona": "h-pamuditha"}).json()
    assert [(c["id"], c["feed"]) for c in listed] == [(LANDING, True)]  # Studio's Source dropdown lists these
