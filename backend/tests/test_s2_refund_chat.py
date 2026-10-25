# test_s2_refund_chat.py: S2 for the refund happy path BDD (website chat), every visit of one conversation.
# Visit 1: Anna's refund request. Visit 2: her "yes, that one" reply. Visit 3: Kafka redelivers visit 1.
# Uses: capture_api.py, orchestrate.py, contracts_signal.py, pii.py, tests/test_s1_refund_chat.py (helpers).
import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate, pii
from app.pipeline.contracts_signal import Signal
from tests.golden import NOW, SEED
from tests.test_s1_refund_chat import FIRST, SECOND, SESSION, send

# Config
TENANT = SEED["tenant_id"]
ANNA = ("Anna", "anna@example.lk")
ANNA_TOKEN = pii.make_token(TENANT, ANNA[1])


# --- Helpers

@pytest.fixture
def lane():
    """S1 and S2 only, so each visit can be checked before anything downstream runs."""
    observe.reset_counts()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    lane.bus.subscribers = {"signals.raw": lane.bus.subscribers["signals.raw"]}
    return lane


@pytest.fixture
def client(lane):
    return TestClient(capture_api.create_app(lane))


def visit(client, lane, message) -> None:
    """Anna sends one chat message; S1 takes it and S2 works through it."""
    assert send(client, message).status_code == 202
    lane.bus.drain()


def redeliver_first(lane) -> None:
    """Kafka delivers at least once: visit 1's K1 arrives at S2 again."""
    lane.bus.redeliver("signals.raw", lane.bus.topics["signals.raw"][0])
    lane.bus.drain()


def signals(lane) -> list[dict]:
    return [envelope.payload for envelope in lane.bus.topics.get("signals.normalized", [])]


# --- Visit 1: "I want a refund for my last order"

def test_visit_1_turns_the_refund_request_into_a_masked_signal(client, lane):
    visit(client, lane, FIRST)
    [signal] = signals(lane)
    assert (signal["kind"], signal["channel"], signal["conversation_id"]) == ("customer_message", "chat", SESSION)
    assert signal["text_masked"] == "I want a refund for my last order"
    assert signal["actor"] == {"type": "customer", "ref": ANNA_TOKEN}
    assert lane.vault[ANNA_TOKEN] == ANNA[1] and signal["sensitivity"] == "confidential"


# --- Visit 2: "yes, that one"

def test_visit_2_joins_the_same_conversation_and_customer(client, lane):
    visit(client, lane, FIRST)
    visit(client, lane, SECOND)
    first, second = signals(lane)
    assert second["text_masked"] == "yes, that one"
    assert second["conversation_id"] == first["conversation_id"] == SESSION
    assert second["actor"] == first["actor"]  # same Anna, same token: S2 reuses visit 1's identity
    assert second["entity_ids"] == first["entity_ids"]  # and the same customer record from the registry
    assert second["signal_id"] != first["signal_id"] and second["dedup_key"] != first["dedup_key"]


def test_visit_2_reuses_the_vault_and_leaves_visit_1_untouched(client, lane):
    visit(client, lane, FIRST)
    vault_after_first, first_before = dict(lane.vault), signals(lane)[0]
    visit(client, lane, SECOND)
    assert lane.vault == vault_after_first  # no new vault entries for the same person
    assert signals(lane)[0] == first_before
