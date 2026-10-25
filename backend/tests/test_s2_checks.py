# test_s2_checks.py: S2 checks beyond the visits: seam logs against K1 and K2, a frozen golden master, random traffic.
# Uses: tests/test_s2_refund_chat.py (lane, visit helpers), pii.py, observe.py, contracts_signal.py.
import json
import logging
import random

from app.pipeline import observe
from app.pipeline.contracts_signal import Signal
from tests.test_s1_refund_chat import FIRST, SECOND, SESSION, send
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
