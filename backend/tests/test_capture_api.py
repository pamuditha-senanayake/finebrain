# test_capture_api.py: S1 over HTTP. Every answer in reference doc section 8 for K1, and that refusals store nothing.
# Uses: app/pipeline/capture_api.py, app/pipeline/orchestrate.py, app/pipeline/observe.py, tests/golden.py.
import logging

import pytest
from fastapi.testclient import TestClient

from app.pipeline import capture_api, fakes, observe, orchestrate
from tests.golden import NOW, SEED, golden, raw_sample

# Config
GMAIL = "conn_gmail_support"
S2_BODY = raw_sample("s2")["raw_body"].encode()


# --- Helpers

@pytest.fixture
def lane():
    observe.reset_counts()
    return orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)


@pytest.fixture
def client(lane):
    return TestClient(capture_api.create_app(lane))


def post(client, connector_id=GMAIL, body=S2_BODY, content_type="message/rfc822", secret=None, headers=None):
    """Send one signal the way a connector would, signed with its secret unless told otherwise."""
    connector = SEED["connectors"].get(connector_id, {})
    signature = capture_api.sign(secret or connector.get("secret", "none"), body)
    sent = {"content-type": content_type, "x-signature": signature, "x-external-id": "gmail_18c2f0a1b9",
            "to": "support@finebase.lk", "subject": "Refund for my Pro monthly plan", "from": "Nimal Perera <nimal.perera@example.lk>", **(headers or {})}
    return client.post(f"/capture/{connector_id}", content=body, headers=sent)


def stored_nothing(lane) -> bool:
    return lane.object_store == {} and "signals.raw" not in lane.bus.topics


# --- Accepted

def test_signed_email_is_stored_and_published(client, lane):
    response = post(client)
    assert response.status_code == 202
    k1 = lane.bus.topics["signals.raw"][0].payload
    expected = golden("s2", "RawSignalEnvelope")
    assert (k1["raw_sha256"], k1["size_bytes"], k1["headers_subset"]) == (expected["raw_sha256"], expected["size_bytes"], expected["headers_subset"])
    assert response.json()["event_id"] == lane.bus.topics["signals.raw"][0].event_id
    assert observe.read_count("s1.captured") == 1


def test_accepted_signal_flows_on_to_a_task(client, lane):
    post(client)
    lane.bus.drain()
    assert len(lane.bus.topics["tasks.created"]) == 1


# --- Refused, and nothing stored

@pytest.mark.parametrize("case, status, reason", [
    ({"connector_id": "conn_nobody"}, 404, "unknown_connector"),
    ({"connector_id": "conn_old_crm"}, 403, "no_active_grant"),
    ({"secret": "wrong-secret"}, 401, "signature"),
    ({"headers": {"x-signature": ""}}, 401, "signature"),
    ({"content_type": "image/png"}, 415, "content_type"),
    ({"headers": {"x-external-id": ""}}, 400, "missing_external_id"),
    ({"body": b"\xff\xfe not utf-8"}, 415, "not_utf8"),
])
def test_refusals_store_nothing(client, lane, case, status, reason):
    response = post(client, **case)
    assert (response.status_code, response.json()["detail"]) == (status, reason)
    assert stored_nothing(lane) and observe.read_count(f"s1.rejected.{reason}") == 1


def test_too_large_is_refused(client, lane, monkeypatch):
    monkeypatch.setattr(capture_api, "MAX_BODY_BYTES", 100)
    assert post(client).status_code == 413 and stored_nothing(lane)


# --- Bus down: 503, then the source's retry succeeds without duplicates

def test_bus_down_answers_503_and_retry_works(client, lane, monkeypatch):
    def bus_down(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    with monkeypatch.context() as patch:
        patch.setattr(lane.bus, "publish", bus_down)
        response = post(client)
    assert (response.status_code, response.headers["retry-after"]) == (503, capture_api.RETRY_AFTER_SECONDS)
    assert "signals.raw" not in lane.bus.topics and observe.read_count("s1.unavailable") == 1

    assert post(client).status_code == 202
    assert len(lane.object_store) == 1 and len(lane.bus.topics["signals.raw"]) == 1


# --- Logs carry ids, never personal data

def test_logs_hold_no_personal_data(client, caplog):
    with caplog.at_level(logging.INFO, logger=observe.LOGGER_NAME):
        post(client)
        post(client, secret="wrong-secret")
    assert '"event": "captured"' in caplog.text and '"reason": "signature"' in caplog.text
    assert not [value for value in ("Nimal", "nimal.perera", "+94") if value in caplog.text]
