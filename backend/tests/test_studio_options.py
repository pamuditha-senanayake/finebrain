# test_studio_options.py: Studio's pick lists come from what the pipeline really serves and checks, and a value outside
# them is flagged. The endpoints are exactly S9's runners, the capabilities exactly what S5 and S7 check (plus any an
# agent already holds, marked), the events per connection. Uses: tests/activity_world.py, api/studio_options.py, run_finish.py.
from types import SimpleNamespace

from app.api.studio_findings import health
from app.api.studio_state import Studio
from app.pipeline import run_finish
from tests.activity_world import LANDING, WF, apply, build, build_landing


def options(client, lane) -> dict:
    return client.get(f"/api/t/{lane.seed['tenant_id']}/studio/options", headers={"x-persona": "h-pamuditha"}).json()


def test_the_endpoints_are_exactly_what_s9_serves():
    client, lane = build()
    served = set(run_finish.tooling(lane, SimpleNamespace(task=None))["runners"]) | {"none"}
    assert {e["id"] for e in options(client, lane)["endpoints"]} == served


def test_the_capabilities_are_what_s5_and_s7_check_and_an_unchecked_one_is_marked():
    client, lane = build()
    build_landing(client, lane)
    apply(client, lane, "agent", {"name": "Odd agent", "fields": {"capabilities": ["kb.read", "billing.peek"]}})
    found = {c["id"]: c["label"] for c in options(client, lane)["capabilities"]}
    assert {"kb.read", "reply.draft", "refund.propose", "escalate"} <= set(found) and found["billing.peek"].endswith("(no check uses it)")
    st = Studio.of(lane)
    assert any("billing.peek" in f["text"] and f["severity"] == "warn" for f in health(st, st.flows[WF])["findings"])


def test_each_connection_lists_the_events_it_sends():
    client, lane = build()
    assert options(client, lane)["events"][LANDING] == ["message.created"]


def test_a_tool_sent_to_an_endpoint_nobody_serves_is_a_break():
    client, lane = build()
    build_landing(client, lane)
    apply(client, lane, "tool", {"fields": {"endpoint": "old_gateway"}}, intent="update", target="tool:reply_customer", workflow=None)
    st = Studio.of(lane)
    assert any("S9 does not serve" in f["text"] and f["severity"] == "break" for f in health(st, st.flows[WF])["findings"])
