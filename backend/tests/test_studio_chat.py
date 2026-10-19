# test_studio_chat.py: the Studio assistant (step 9e) with a scripted stand-in for Claude. Its tools only draft: a change
# comes back reviewed by the server as a card, a refused draft goes back to Claude to fix, a story is drafted then
# confirmed into a proposal, cards and workflow switches steer the screen, and nothing changes without Confirm.
# Uses: app/api/studio_chat.py, tests/studio_helpers.py.
from types import SimpleNamespace

from app.api.studio_chat import NO_CLAUDE, messages_of
from app.api.routes import create_api_app
from fastapi.testclient import TestClient
from tests.studio_helpers import FOUNDER, HQ, REFUND_WF, TENANT, build, node

# Config
WINDOW = {"intent": "update", "kind": "policy", "targetId": "policy_refund", "workflowId": REFUND_WF, "patch": {"fields": {"param.days": 45}}}
CASE = {"title": "Late annual refund", "given": ["an annual plan bought 40 days ago"], "when": "the customer asks for a refund", "then": ["it escalates"], "goal": "a pro rata refund is offered"}


class Block(SimpleNamespace):
    def model_dump(self):
        return dict(vars(self))


def use(name: str, args: dict, n: int = 1) -> Block:
    return Block(type="tool_use", id=f"tu_{name}_{n}", name=name, input=args)


def scripted(*rounds):
    """A chatter that answers each round with the next list of blocks, and keeps what it was sent."""
    seen = []

    def chatter(system, messages, tools):
        seen.append({"system": system, "messages": [dict(m) for m in messages]})
        return SimpleNamespace(content=rounds[len(seen) - 1])
    return chatter, seen


def ask(lane, chatter, message: str, story=None, workflow: str = REFUND_WF):
    client = TestClient(create_api_app(lane, HQ, None, chatter))
    body = {"workflowId": workflow, "message": message, "focus": None, "history": [], "story": story}
    return client.post(f"/api/t/{TENANT}/studio/chat", json=body, headers={"x-persona": FOUNDER})


# --- Drafting changes

def test_a_proposal_is_reviewed_by_the_server_and_nothing_changes():
    _, lane = build()
    chatter, seen = scripted([use("propose_change", WINDOW), use("reply", {"answer": "Here is the change, sir.", "suggestions": ["Why C3?"]})])
    body = ask(lane, chatter, "make the refund window 45 days").json()
    assert body["proposal"]["review"]["criticality"] == 3 and body["proposal"]["changes"][0]["after"] == "45 days"
    assert body["answer"] == "Here is the change, sir." and body["suggestions"][0]["label"] == "Why C3?"
    assert node(lane, "policy", "policy_refund")["window_days"] == 30
    assert "address the person as sir" in seen[0]["system"] and "<context>" in seen[0]["messages"][-1]["content"]


def test_a_refused_draft_goes_back_to_claude_once():
    _, lane = build()
    nothing = {**WINDOW, "patch": {"fields": {"param.days": 30}}}
    chatter, seen = scripted([use("propose_change", nothing)], [use("propose_change", WINDOW, 2), use("reply", {"answer": "Fixed, sir."})])
    body = ask(lane, chatter, "change the window").json()
    error = seen[1]["messages"][-1]["content"][0]
    assert error["is_error"] is True and "Nothing would change" in error["content"]
    assert body["proposal"]["changes"][0]["after"] == "45 days"


# --- Stories

def test_a_story_is_drafted_then_confirmed_into_a_proposal():
    _, lane = build()
    story_args = {"workflowId": REFUND_WF, "name": "Refund handling", "problem": "Late refunds wait for days", "today": "A person reads each one", "scenarios": [CASE]}
    chatter, _ = scripted([use("draft_story", story_args), use("reply", {"answer": "Does this match, sir?"})])
    draft = ask(lane, chatter, "late annual refunds sit for days").json()["story"]
    assert draft["story"]["scenarios"][0]["id"].startswith("sc-") and draft["workflowId"] == REFUND_WF
    chatter, _ = scripted([use("confirm_story", {}), use("reply", {"answer": "Ready to confirm, sir."})])
    proposal = ask(lane, chatter, "yes, looks right", story=draft).json()["proposal"]
    assert proposal["input"]["patch"]["story"]["scenarios"][0]["title"] == "Late annual refund"
    assert proposal["changes"][-1]["field"] == "story.scenarios"


# --- Steering the screen

def test_cards_and_switching():
    _, lane = build()
    chatter, _ = scripted([use("show_items", {"ids": ["agent_refund_worker", "nope"]}), use("switch_workflow", {"workflowId": "wf_act_billing_question"}),
                           use("reply", {"answer": "Opened billing, sir."})])
    body = ask(lane, chatter, "show me the agent, then billing").json()
    assert [c["title"] for c in body["cards"]] == ["Refund worker"] and body["workflowId"] == "wf_act_billing_question"


def test_without_claude_it_points_to_the_forms():
    _, lane = build()
    assert ask(lane, None, "hello").json()["answer"] == NO_CLAUDE


def test_history_alternates_and_ends_with_the_new_message():
    history = [{"role": "assistant", "text": "Hi"}, {"role": "user", "text": "a"}, {"role": "user", "text": "b"}, {"role": "assistant", "text": "c"}, {"role": "user", "text": "d"}]
    messages = messages_of(history, "new")
    assert [m["role"] for m in messages] == ["user", "assistant", "user"] and messages[0]["content"] == "a\nb" and messages[-1]["content"] == "new"
