# capture_api.py: S1 Capture over HTTP (port 8001). Checks connector, grant, size, type and signature,
# then stores the raw body and publishes K1. Every refusal stores nothing (reference doc section 8).
# Used by: tests/test_capture_api.py. Uses: orchestrate.py (capture_signal), stages_intake.py (SAFE_HEADERS), observe.py.
import hashlib
import hmac

from fastapi import FastAPI, HTTPException, Request

from app.pipeline import orchestrate
from app.pipeline.observe import count, log_event, touch
from app.pipeline.stages_intake import SAFE_HEADERS

# Config
MAX_BODY_BYTES = 25 * 1024 * 1024  # larger files take the upload path
ALLOWED_CONTENT_TYPES = {"message/rfc822", "application/json", "text/plain"}
SIGNATURE_HEADER = "x-signature"  # "sha256=<hex of HMAC-SHA256(secret, body)>"
EXTERNAL_ID_HEADER = "x-external-id"  # the source's own message id, used for dedup in S2
RETRY_AFTER_SECONDS = "5"


def sign(secret: str, body: bytes) -> str:
    """The signature a connector sends with each body."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def refuse(status: int, reason: str, connector_id: str) -> HTTPException:
    """Count and log a refusal, then build the HTTP answer. Nothing has been stored at this point."""
    count(f"s1.rejected.{reason}")
    log_event("S1", "rejected", reason=reason, connector_id=connector_id, status=status)
    return HTTPException(status_code=status, detail=reason)


def check_request(connector_id: str, connector: dict | None, content_type: str, body: bytes, headers) -> None:
    """Every check S1 makes before it stores anything, cheapest first."""
    if connector is None:
        raise refuse(404, "unknown_connector", connector_id)
    if not connector["grant_active"]:
        raise refuse(403, "no_active_grant", connector_id)
    if len(body) > MAX_BODY_BYTES:
        raise refuse(413, "too_large", connector_id)
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise refuse(415, "content_type", connector_id)
    if not hmac.compare_digest(headers.get(SIGNATURE_HEADER, ""), sign(connector["secret"], body)):
        raise refuse(401, "signature", connector_id)  # compare_digest: timing does not leak the signature
    if not headers.get(EXTERNAL_ID_HEADER):
        raise refuse(400, "missing_external_id", connector_id)


def build_raw(connector_id: str, connector: dict, content_type: str, body: bytes, headers) -> dict:
    """The raw signal shape S1 stores, keeping only headers without personal data."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise refuse(415, "not_utf8", connector_id) from None
    return {
        "connector_id": connector_id, "grant_id": connector["grant_id"], "source_type": connector["source_type"],
        "external_id": headers[EXTERNAL_ID_HEADER], "content_type": content_type, "raw_body": text,
        "headers_subset": {name: headers[name] for name in SAFE_HEADERS if name in headers},
    }


def publish_or_503(lane, raw: dict) -> dict:
    """Store and publish. If the bus is down, answer 503 so the source retries; a retry lands on the same object."""
    try:
        envelope = orchestrate.capture_signal(lane, raw)
    except Exception as error:  # one catch at the entry point: the bus or the object store is down
        count("s1.unavailable")
        log_event("S1", "unavailable", connector_id=raw["connector_id"], error=type(error).__name__)
        raise HTTPException(status_code=503, detail="unavailable", headers={"Retry-After": RETRY_AFTER_SECONDS}) from None
    count("s1.captured")
    count(f"s1.captured.{raw['connector_id']}")
    touch(f"s1.last_event.{raw['connector_id']}", envelope.occurred_at.isoformat())
    log_event("S1", "captured", connector_id=raw["connector_id"], event_id=envelope.event_id, correlation_id=envelope.correlation_id)
    return {"event_id": envelope.event_id, "correlation_id": envelope.correlation_id}


def create_app(lane) -> FastAPI:
    """The capture service for one lane, on its own (port 8001 in production)."""
    app = FastAPI(title="finebrain capture")
    register(app, lane)
    return app


def register(app: FastAPI, lane) -> None:
    """Add POST /capture/{connector_id} to an app. Local development mounts it on the main API."""

    @app.post("/capture/{connector_id}", status_code=202)
    async def capture(connector_id: str, request: Request) -> dict:
        body = await request.body()
        connector = lane.seed["connectors"].get(connector_id)
        connector = connector if isinstance(connector, dict) else None  # the "_about" note is not a connector
        content_type = request.headers.get("content-type", "").split(";")[0].strip()
        check_request(connector_id, connector, content_type, body, request.headers)
        return publish_or_503(lane, build_raw(connector_id, connector, content_type, body, request.headers))
