# test_studio_repairs.py: what went wrong when Landing page chat first went live, each now caught or repaired. A skill
# saved with no tools is a break in Studio, and if it runs anyway S4 tells the visitor a person will reply instead of
# leaving them in silence. Capabilities written as their labels ("Reply to customers") are saved as the ids S5 and S7
# check. A policy whose wording never reached knowledge gets it on the next change. Uses: tests/activity_world.py.
from app.api.studio_findings import health
from app.api.studio_state import Studio
from app.pipeline import conn_call, conversation_log
from tests.activity_world import LANDING, STATEMENT, WF, answer_with, apply, build, build_landing, node, stand_in_portal, visitor
from tests.s6_world import scripted


def test_a_skill_with_no_tools_is_a_break_and_the_visitor_still_hears_back(monkeypatch):
    client, lane = build()
    posted = stand_in_portal(monkeypatch)
    ids = build_landing(client, lane)
    apply(client, lane, "skill", {"fields": {"tools": []}}, intent="update", target=ids["skill"])
    st = Studio.of(lane)
    assert any("lists no tools" in f["text"] and f["severity"] == "break" for f in health(st, st.flows[WF])["findings"])
    visitor(lane, "hi")  # S4 refuses: recipe_missing
    assert [p["body"] for p in posted] == [conversation_log.HANDOFF_TEXT]
    shown = client.get(f"/api/t/{lane.seed['tenant_id']}/conversations/conn_landing_chat:c-landing-1", headers={"x-persona": "h-pamuditha"}).json()
    assert [m["from"] for m in shown["messages"]] == ["customer", "system"]


def test_capabilities_written_as_labels_are_saved_as_ids_and_an_unknown_one_is_a_break():
    client, lane = build()
    build_landing(client, lane)
    agent = apply(client, lane, "agent", {"name": "Helper", "fields": {"capabilities": ["Read knowledge", "Reply to customers", "do anything"]}})
    assert node(lane, "agent", agent)["capabilities"] == ["kb.read", "reply.draft", "do anything"]
    st = Studio.of(lane)
    assert any('"do anything"' in f["text"] and f["severity"] == "break" for f in health(st, st.flows[WF])["findings"])


def test_a_policy_without_its_wording_in_knowledge_gets_it_on_the_next_change():
    client, lane = build()
    ids = build_landing(client, lane)
    statement = node(lane, "knowledge", f"{ids['policy']}_statement")
    lane.graph.put("knowledge", f"{ids['policy']}_statement", statement["_ref"]["version"] + 1, "cmt_old", {"_closed": True})  # as if saved before
    assert node(lane, "knowledge", f"{ids['policy']}_statement") is None
    apply(client, lane, "sensor", {"description": "Landing chat"}, intent="update", target=ids["sensor"])
    assert node(lane, "knowledge", f"{ids['policy']}_statement")["text"] == STATEMENT


def test_a_site_whose_reply_names_no_body_gets_the_text_under_its_own_feed_name(monkeypatch):
    client, lane = build()
    connection = conn_call.load(lane, LANDING)
    manifest = connection.manifest.model_copy(deep=True)
    manifest.actions["reply"] = manifest.actions["reply"].model_copy(update={"body": None})  # as finebaselabs.com answered
    conn_call.save(lane, connection.model_copy(update={"manifest": manifest}))
    posted = stand_in_portal(monkeypatch)
    ids = build_landing(client, lane)
    lane.model, _ = scripted(answer_with(ids["policy"], "Hi! What are you building?"))
    visitor(lane, "hola amiga")
    assert [set(p) - {"id", "at"} for p in posted] == [{"body"}] and posted[0]["body"] == "Hi! What are you building?"
