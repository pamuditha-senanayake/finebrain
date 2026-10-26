# s1_to_s10_refund.py: Amara's refund chat through all ten stages, for real. Her messages enter through the real S1 inbound
# path of the Finebase Labs portal connection, real Claude reasons (S6) and grades (S7), the stages run on Postgres, Valkey,
# Redpanda and SeaweedFS, the brain's replies land in her real portal conversation, and S9 refunds in the shop's own
# database (finebase_shop). Her orders are in USD and the automatic limit is in LKR, so a person approves (S8).
# Prints, per message: what Amara wrote, what each stage did, her chat's newest brain message, and the shop's order.
# Edit MESSAGES below, then run from backend/:  uv run python -m demos.s1_to_s10_refund   (needs Docker, ANTHROPIC_API_KEY,
# the portal guide with its key, and network outside the sandbox). Uses: adapters.py, llm.py, orchestrate.py, tests/s7_world.py, tests/test_s9_chat_real.py.
import json
import uuid
from datetime import datetime, timezone

import psycopg

from app.pipeline import conn_call, llm, orchestrate
from app.pipeline.adapters import missing_infra, real_adapters
from app.pipeline.contracts_run import Decision
from app.pipeline.kafka_admin import delete_prefixed_topics
from scripts import shop_db
from scripts.test_keys import ENV_PATH, load_env_file
from tests.s5_world import world_seed
from tests.s7_world import full_lane
from tests.test_s5_real import S5_PARTS, parts
from tests.test_s9_chat_real import AMARA_CHAT, PORTAL, amara_types, connect_portal, portal_is_up

# --- Input: change anything here
MESSAGES = ["I want a refund for my last order", "yes, that one"]
ORDER = "ORD-10482"  # her newest order, Agent Gateway, USD 129: shown after each message
APPROVER = "head_of_cs"  # the person who decides a refund the policy cannot clear alone


def shop_now() -> str:
    """The order's status and every refund on it, read as the shop's own staff."""
    with psycopg.connect(shop_db.owner_url()) as db:
        status = db.execute("SELECT status FROM shop.orders WHERE id = %s", (ORDER,)).fetchone()[0]
        refunds = db.execute("SELECT r.id, r.amount_minor, o.currency, r.status FROM shop.refunds r JOIN shop.orders o ON o.id = r.order_id WHERE r.order_id = %s", (ORDER,)).fetchall()
    return f"{ORDER} is {status}; refunds: {refunds or 'none'}"


def her_chat_now(lane) -> str:
    """The newest brain message in her real portal conversation, read back from the portal."""
    messages = conn_call.call(lane, conn_call.load(lane, PORTAL), "conversation", {"conversation_id": AMARA_CHAT})["messages"]
    brain = [m for m in messages if m["sender"] != "customer"]
    return f"{brain[-1]['body']!r} (id {brain[-1]['id']})" if brain else "nothing yet"


def run_line(lane, record: dict) -> str:
    """S6's action and S7's route from the trace S10 wrote, then S10's outcome."""
    trace = json.loads(lane.object_store[record["trace_object_uri"]])
    action, route = trace.get("action") or {}, (trace.get("verdict") or {}).get("route")
    return (f"S6 {action.get('action_type')}: {json.dumps(action.get('arguments', {}))[:150]}\n  S7 route {route}; "
            f"S10 run {record['run_id']} {record['outcome']}, decided by {record.get('decided_by')}")


def what_happened(lane, seen: dict) -> list[str]:
    """New approvals, S9 results and S10 records since the last look, in plain lines."""
    lines = []
    for topic, show in (("approvals.requested", lambda p: f"S8 asks {p['dri_id']} to approve ({p['approval_id']})"),
                        ("actions.executed", lambda p: f"S9 {p['tool_id']} {p['status']}: {p['response_summary']} (ref {p['external_ref']})"),
                        ("runs.completed", lambda p: run_line(lane, p))):
        envelopes = lane.bus.topics.get(topic, [])
        lines += [show(e.payload) for e in envelopes[seen.get(topic, 0):]]
        seen[topic] = len(envelopes)
    return lines


def show(lane, seen: dict, heading: str) -> None:
    print(heading)
    print("\n".join(f"  {line}" for line in what_happened(lane, seen)) or "  (nothing ran)")
    print(f"  her chat: {her_chat_now(lane)}\n  shop: {shop_now()}\n")


if __name__ == "__main__":
    load_env_file(ENV_PATH)
    if missing_infra(S5_PARTS) or not portal_is_up():
        raise SystemExit("Start Docker, keep the portal guide with its key, and run outside the sandbox")
    tag = uuid.uuid4().hex[:8]
    lane = full_lane(real_adapters(parts(), topic_prefix=f"demo{tag}."), seed={**world_seed(), "tenant_id": f"demo_{tag}"})
    lane.model, lane.grade = llm.make_tool_caller(), llm.make_grader()
    lane.tooling["send_email"] = None  # as in production: replies go into her chat or to a person
    connect_portal(lane)
    seen: dict = {}
    print(f"before: {shop_now()}\n")
    try:
        for text in MESSAGES:
            lane.now = lane.bus.now = datetime.now(timezone.utc)  # her orders are dated by the real clock
            amara_types(lane, text)
            show(lane, seen, f"Amara: {text}")
        for request in [e.payload for e in lane.bus.topics.get("approvals.requested", [])]:
            orchestrate.decide(lane, Decision(approval_id=request["approval_id"], decision="approve", decided_by=[APPROVER], decided_at=lane.now))
            lane.bus.drain()
            show(lane, seen, f"{APPROVER} approves {request['approval_id']}")
    finally:
        delete_prefixed_topics(f"demo{tag}.")
