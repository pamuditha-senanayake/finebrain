# stages_intake.py: S1 Capture (raw signal to K1) and S2 Normalize (K1 to masked K2).
# Used by: tests/test_stages.py. Uses: contracts_signal.py.
import hashlib
import json
import re
from datetime import datetime
from email.utils import parseaddr

from app.pipeline.contracts_signal import Actor, Entity, RawSignalEnvelope, Signal, Subject

# Config
SAFE_HEADERS = ("to", "subject", "filename", "session")  # never "from": it names a person
FILE_EXTENSIONS = {"message/rfc822": ".eml", "application/json": ".json", "text/plain": ".txt"}
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_PATTERN = re.compile(r"\+94[\d ]{9,12}\d")
NIC_PATTERN = re.compile(r"\b(?:\d{12}|\d{9}[VvXx])\b")
MONEY_PATTERN = re.compile(r"LKR ([\d,]+)")
PAYMENT_REF_PATTERN = re.compile(r"\bpay_[A-Za-z]+_\d{8}_\d{4}\b")
DATE_PATTERN = re.compile(r"\bon (\d{1,2} [A-Z][a-z]+ \d{4})")


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
    return RawSignalEnvelope(
        connector_id=raw["connector_id"], grant_id=raw["grant_id"], source_type=raw["source_type"],
        external_id=raw["external_id"], received_at=now, signature_verified=True,
        raw_object_uri=uri, raw_sha256=hashlib.sha256(body).hexdigest(),
        content_type=raw["content_type"], size_bytes=len(body),
        headers_subset={key: value for key, value in raw["headers_subset"].items() if key in SAFE_HEADERS},
    )


# --- S2 helpers

def read_message(content_type: str, body: str) -> tuple[str, str, str]:
    """Return sender name, sender email and message text, for email or web chat."""
    if content_type == "application/json":
        chat = json.loads(body)
        return chat["visitor_name"], chat["visitor_email"], chat["text"]
    headers, _, text = body.partition("\n\n")
    from_line = next(line for line in headers.splitlines() if line.startswith("From:"))
    name, email = parseaddr(from_line.removeprefix("From:"))
    return name, email, text


def make_token(tenant_id: str, value: str) -> str:
    """Same value gives the same token, so the vault and dedup stay stable."""
    return "pii_tok_" + hashlib.sha256(f"{tenant_id}:{value}".encode()).hexdigest()[:22]


def mask_text(text: str, known: list[str], tenant_id: str, vault: dict[str, str]) -> tuple[str, list[str]]:
    """Swap every personal value for its token. Returns the masked text and tokens in order."""
    found = EMAIL_PATTERN.findall(text) + NIC_PATTERN.findall(text) + PHONE_PATTERN.findall(text)
    tokens = []
    for value in dict.fromkeys(known + found):  # keeps order, drops repeats
        token = make_token(tenant_id, value)
        vault[token] = value
        text = text.replace(value, token)
        tokens.append(token)
    return " ".join(text.split()), tokens


def find_entities(text: str) -> list[Entity]:
    """Pull out the money, payment reference and purchase date that S3 and S6 need."""
    money = [Entity(type="money", value_or_token=f"LKR {raw.replace(',', '')}", confidence=0.9) for raw in MONEY_PATTERN.findall(text)]
    refs = [Entity(type="payment_ref", value_or_token=ref, confidence=0.95) for ref in PAYMENT_REF_PATTERN.findall(text)]
    dates = [Entity(type="purchase_date", value_or_token=datetime.strptime(day, "%d %B %Y").date().isoformat(), confidence=0.9) for day in DATE_PATTERN.findall(text)]
    return money + refs + dates


def choose_subject(entities: list[Entity], customer_token: str) -> Subject:
    """A payment is the most useful subject; without one, the customer is."""
    refs = [entity.value_or_token for entity in entities if entity.type == "payment_ref"]
    if refs:
        return Subject(entity_type="payment", entity_ref=refs[0])
    return Subject(entity_type="customer", entity_ref=customer_token)


# --- S2 Normalize

def normalize(
    k1: RawSignalEnvelope, raw_event_id: str, tenant_id: str, object_store: dict[str, bytes],
    vault: dict[str, str], seen_keys: set[str], new_id,
) -> Signal | None:
    """S2: turn K1 into a masked K2, or None when this signal was already processed."""
    # Step 1: drop redeliveries, keyed on the source's own id
    dedup_key = f"{tenant_id}:{k1.source_type}:{k1.external_id}"
    if dedup_key in seen_keys:
        return None

    # Step 2: read the message and mask every personal value
    name, email, text = read_message(k1.content_type, object_store[k1.raw_object_uri].decode())
    text_masked, tokens = mask_text(text, [name, email], tenant_id, vault)
    entities = find_entities(text_masked)
    customer_token = make_token(tenant_id, email)

    # Step 3: describe it as K2, then mark it seen so a failure above can be retried
    signal = Signal(
        signal_id=new_id("sig"), raw_event_id=raw_event_id, kind="customer_message", channel=k1.source_type,
        actor=Actor(type="customer", ref=customer_token), subject=choose_subject(entities, customer_token),
        text_masked=text_masked, language="en", entities=entities, pii_tokens=tokens,
        sensitivity="restricted" if NIC_PATTERN.search(text) else "confidential", dedup_key=dedup_key,
    )
    seen_keys.add(dedup_key)
    return signal
