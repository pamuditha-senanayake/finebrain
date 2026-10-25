# test_s2_checks.py: S2 checks beyond the visits: seam logs against K1 and K2, a frozen golden master, random traffic,
# and the two bugs the S1 to S3 verification found (slow email search, visitors without an email merging).
# Uses: tests/test_s2_refund_chat.py (lane, visit helpers), capture_api.py, pii.py, observe.py, contracts_signal.py.
import json
import logging
import random
import time

from app.pipeline import capture_api, observe, pii
from app.pipeline.contracts_signal import Signal
from tests.golden import SEED
from tests.test_s1_refund_chat import CHAT, FIRST, SECOND, SESSION, send
from tests.test_s2_refund_chat import ANNA, ANNA_TOKEN, client, lane, signals, visit  # noqa: F401 (fixtures)

# Config
ANNA_ENTITY = "ent_customer_12bd44d2f0e6"
FROZEN_SHARED = {  # what both visits share, reviewed by hand once, then frozen
    "kind": "customer_message", "channel": "chat", "actor": {"type": "customer", "ref": ANNA_TOKEN},
    "subject": {"entity_type": "customer", "entity_ref": ANNA_TOKEN}, "language": "en", "entities": [], "attachments": [],
    "pii_tokens": ["pii_tok_5e7c09ccb6145ee4ef78a0", ANNA_TOKEN], "sensitivity": "confidential", "flags": [],
    "entity_ids": [ANNA_ENTITY], "conversation_id": SESSION, "domain": "customer_care",
}
FROZEN = [
    {**FROZEN_SHARED, "text_masked": "I want a refund for my last order", "dedup_key": "finebase_labs:chat:chat_msg_anna_1"},
    {**FROZEN_SHARED, "text_masked": "yes, that one", "dedup_key": "finebase_labs:chat:chat_msg_anna_2"},
]
VOLATILE = ("signal_id", "raw_event_id")  # ids come from a counter, so they are checked by the rules instead


# --- Seam logs: what came in from S1 and what went out to S3, no personal data

def test_seam_logs_match_k1_and_k2(client, lane, caplog):
    with caplog.at_level(logging.INFO, logger=observe.LOGGER_NAME):
        visit(client, lane, FIRST)
    lines = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    seam_in = next(line for line in lines if line["stage"] == "S2" and line["event"] == "seam_in")
    seam_out = next(line for line in lines if line["stage"] == "S2" and line["event"] == "seam_out")
    k1, k2 = lane.bus.topics["signals.raw"][0].payload, signals(lane)[0]
    assert (seam_in["connector_id"], seam_in["external_id"], seam_in["source_type"]) == (k1["connector_id"], k1["external_id"], k1["source_type"])
    assert {key: seam_out[key] for key in ("signal_id", "kind", "channel", "dedup_key", "conversation_id")} == {key: k2[key] for key in ("signal_id", "kind", "channel", "dedup_key", "conversation_id")}
    assert not [value for value in ANNA if value in caplog.text]


# --- Golden master: Anna's two visits must keep producing exactly this

def test_visits_match_the_frozen_result(client, lane):
    visit(client, lane, FIRST)
    visit(client, lane, SECOND)
    produced = [{key: value for key, value in signal.items() if key not in VOLATILE} for signal in signals(lane)]
    assert produced == FROZEN


# --- Random traffic: many messages in Anna's chat, personal data and resends mixed in

def random_conversation(generator, number: int) -> list[dict]:
    """A few messages, some with personal data inside, the first one maybe resent by the webhook."""
    email = f"customer{number}@example.lk"
    messages = [{"id": f"chat_{number}_{turn}", "text": generator.choice(["refund please", f"mail me at {email}", "call 077 123 4567", "yes"])} for turn in range(generator.randint(1, 4))]
    return messages + ([messages[0]] if generator.random() < 0.3 else [])


def test_rules_hold_for_random_conversations(client, lane):
    generator = random.Random(2026)  # fixed seed so a failure can be replayed
    sent_ids = []
    for number in range(100):
        for message in random_conversation(generator, number):
            assert send(client, message).status_code == 202
            sent_ids.append(message["id"])
    lane.bus.drain()
    produced = signals(lane)
    assert len(produced) == len(set(sent_ids))  # one signal per distinct message: none lost, none doubled
    assert len({signal["dedup_key"] for signal in produced}) == len(produced)
    assert all(Signal.model_validate(signal).conversation_id == SESSION for signal in produced)
    assert not [signal for signal in produced if "@example.lk" in str(signal) or "077 123 4567" in str(signal)]


# --- Long text without spaces: finding personal data stays fast (verification test 5)

def test_long_text_without_spaces_stays_fast():
    """30 KB with no spaces once took 3.6 s in the email search; it must stay far inside the 800 ms budget."""
    text = "refund please " + "a" * 30_000 + " mail kamal@example.lk"
    started = time.perf_counter()
    found = pii.find_personal(text, ANNA[0], ANNA[1])
    assert time.perf_counter() - started < 0.2
    assert ("email", "kamal@example.lk") in found  # an email after the long run is still found


# --- Chat visitors without an email (verification test 10)

def send_without_email(client, external_id: str, name: str, session: str | None):
    """A chat message whose visitor gave no email, in the given chat session (or none)."""
    body = json.dumps({"visitor_name": name, "visitor_email": None, "text": "refund please"}).encode()
    headers = {"content-type": "application/json", "x-external-id": external_id, "x-signature": capture_api.sign(SEED["connectors"][CHAT]["secret"], body)}
    return client.post(f"/capture/{CHAT}", content=body, headers={**headers, **({"session": session} if session else {})})


def test_visitors_without_email_stay_separate_customers(client, lane):
    """Two chats without an email are two customers; two messages in one chat are the same one."""
    for external_id, name, session in (("anon_1", "Kamal Silva", "sess_a"), ("anon_2", "Nimali Perera", "sess_b"), ("anon_3", "Kamal Silva", "sess_a")):
        assert send_without_email(client, external_id, name, session).status_code == 202
    lane.bus.drain()
    first, second, third = signals(lane)
    assert first["actor"]["ref"] != second["actor"]["ref"] and first["entity_ids"] != second["entity_ids"]
    assert first["actor"] == third["actor"] and first["entity_ids"] == third["entity_ids"]


def test_visitor_without_email_or_session_is_dead_lettered(client, lane):
    """Nothing tells this visitor apart from any other, so S2 refuses it rather than guess."""
    assert send_without_email(client, "anon_x", "Kamal Silva", None).status_code == 202
    lane.bus.drain()
    [letter] = lane.bus.dead_letters("signals.raw")
    assert (letter.error_code, letter.retryable) == ("ParseError", False) and signals(lane) == []
