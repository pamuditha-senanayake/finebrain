# s5_world.py: the world S5 tests run in. The golden seed plus samples/s5_world.json (policy history, a future policy,
# a restricted note, agents with other rights), the real shop database from scripts/shop_db.py connected live through the
# read-only door, and helpers that send a message through the real S1 to S3 and ask S5 exactly as S4's run does.
# Uses: orchestrate.py, run_steps.py (query_for), retrieve_case.py, conn_call.py, scripts/shop_db.py, tests/test_s1_refund_chat.py.
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, conn_call, fakes, observe, orchestrate, retrieve_case, run_steps, stages_orchestrate, store_postgres
from app.pipeline.conn_call import Connection
from app.pipeline.conn_spec import DatabaseSpec, OrderMap
from app.pipeline.contracts_signal import TaskRequest
from scripts import shop_db
from tests.golden import NOW, SEED
from tests.test_s1_refund_chat import CHAT, SESSION

# Config
WORLD = json.loads((Path(__file__).resolve().parents[1] / "samples" / "s5_world.json").read_text())
SHOP = "conn_shop_db"
V4_STARTS = next(k["valid_from"] for k in WORLD["knowledge"] if k["item_id"] == "item_policy_window_v4")


def world_seed(seed: dict = SEED) -> dict:
    """The seed with the world added. The 30 day window closes when the 45 day one starts, as a release would close it."""
    knowledge = [{**k, "valid_to": V4_STARTS} if k["item_id"] == "item_policy_window" else k for k in seed["knowledge"]]
    refund_agent = {**seed["agents"]["agent_refund_worker"], "capabilities": [*seed["agents"]["agent_refund_worker"]["capabilities"], "reply.draft"]}
    agents = {**seed["agents"], "agent_refund_worker": refund_agent, **WORLD["agents"]}  # it must answer in the chat, as staff grant in Studio
    return {**seed, "knowledge": knowledge + WORLD["knowledge"], "agents": agents}


needs_postgres = pytest.mark.skipif(not store_postgres.database_is_up(), reason="Postgres is not running: the shop database lives there")


# --- Building the lane

def connect_shop(lane, url: str | None = None, status: str = "live", orders_map: OrderMap | None = None) -> Connection:
    """The shop's database as a live connection, signed in as the read-only user the shop handed over."""
    connection = Connection(connection_id=SHOP, name="Finebase shop database", purpose="orders", kind="database", status=status,
                            database=DatabaseSpec(engine="postgres", schemas=["shop"]), orders_map=orders_map or OrderMap(), created_by="h-pamuditha")
    conn_call.save(lane, connection)
    conn_call.set_secret(lane, connection, "database_url", url or shop_db.reader_url())
    return connection


def make_lane(make_adapters=None, seed: dict | None = None, shop: bool = True):
    """Real S1 to S3, then S4 stops (the test asks S5 itself). The shop's database is reset to the sample world."""
    observe.reset_counts()
    options = {"make_adapters": make_adapters} if make_adapters else {}
    lane = orchestrate.build_lane(seed or world_seed(), fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW, **options)
    lane.bus.subscribers.pop("tasks.created")
    if shop:
        shop_db.setup()
        connect_shop(lane)
    return lane


# --- Sending a message and asking S5

def visitor_says(lane, message: dict, email: str | None = "anna@example.lk", session: str = SESSION, name: str = "Anna") -> dict | None:
    """One chat message through the webhook and the real S1, S2 and S3. Returns the task S3 made for it, if any."""
    before = len(lane.bus.topics.get("tasks.created", []))
    body = json.dumps({"visitor_name": name, "visitor_email": email, "text": message["text"], "sent_at": "2026-10-10T09:55:00+05:30"}).encode()
    headers = {"content-type": "application/json", "x-external-id": message["id"], "session": session,
               "x-signature": capture_api.sign(lane.seed["connectors"][CHAT]["secret"], body)}
    assert TestClient(capture_api.create_app(lane)).post(f"/capture/{CHAT}", content=body, headers=headers).status_code == 202
    lane.bus.drain()
    created = lane.bus.topics.get("tasks.created", [])
    return created[-1].payload if len(created) > before else None


def query_for(lane, task: dict, agent_id: str | None = None, **change):
    """K4 exactly as S4's run builds it (run_steps.query_for), for this task's agent or another one."""
    principal = stages_orchestrate.principal_of(lane, agent_id or task["agent_id"])
    signal = run_steps.signal_of(lane, task["signal_ids"][0])
    query = run_steps.query_for(lane, TaskRequest.model_validate(task), signal, principal, "run_s5_test")
    return query.model_copy(update=change)


def ask(lane, query):
    """S5 for a run: the bundle and the access decision."""
    return retrieve_case.retrieve_for_run(lane, query)


def ids(bundle) -> set[str]:
    return {item.item_id for item in bundle.items}


def text_of(bundle, item_id: str) -> str:
    return next(item.text for item in bundle.items if item.item_id == item_id)
