# stages_intake.py: S1 Capture: store the raw body once and describe it as K1. S2 lives in stages_normalize.py.
# Used by: orchestrate.py, capture_api.py (SAFE_HEADERS), tests. Uses: contracts_signal.py, observe.py (seam log).
import hashlib
from datetime import datetime

from app.pipeline.contracts_signal import RawSignalEnvelope
from app.pipeline.observe import log_seam

# Config
SAFE_HEADERS = ("to", "subject", "filename", "session", "uploaded_by")  # never "from": it names a person
FILE_EXTENSIONS = {"message/rfc822": ".eml", "application/json": ".json", "text/plain": ".txt"}


class CaptureRejected(Exception):
    """S1 refuses a signal. The caller answers 401 and nothing is stored."""


# --- S1 Capture

def capture(raw: dict, tenant_id: str, object_store: dict[str, bytes], now: datetime) -> RawSignalEnvelope:
    """S1: verify, store the raw body once, and describe it as K1."""
    # Step 1: refuse unverified signals before anything is stored
    if not raw.get("signature_ok", True):
        raise CaptureRejected("bad signature")

    # Step 2: store under a path that stays the same on every redelivery
    body = raw["raw_body"].encode()
    extension = FILE_EXTENSIONS.get(raw["content_type"], ".bin")
    uri = f"s3://brain/{tenant_id}/raw/{now:%Y/%m/%d}/{raw['external_id']}{extension}"
    object_store[uri] = body

    # Step 3: describe it, keeping only headers without personal data
    k1 = RawSignalEnvelope(
        connector_id=raw["connector_id"], grant_id=raw["grant_id"], source_type=raw["source_type"],
        external_id=raw["external_id"], received_at=now, signature_verified=True,
        raw_object_uri=uri, raw_sha256=hashlib.sha256(body).hexdigest(),
        content_type=raw["content_type"], size_bytes=len(body),
        headers_subset={key: value for key, value in raw["headers_subset"].items() if key in SAFE_HEADERS},
    )

    # Step 4: log the seam; the body stays out of it because it can hold personal data
    log_seam("S1", {key: value for key, value in raw.items() if key != "raw_body"}, k1.model_dump(mode="json"))
    return k1
