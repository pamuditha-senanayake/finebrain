# stages_normalize.py: S2 Normalize. Reads the raw body (email, chat or upload), masks personal data,
# flags likely prompt injection, and builds K2. Failures follow reference doc section 8 (K2).
# Used by: orchestrate.py, tests. Uses: readers.py, pii.py, observe.py, contracts_signal.py.
import hashlib
import re
from datetime import datetime

from app.pipeline import pii
from app.pipeline.contracts_signal import Actor, Attachment, Entity, RawSignalEnvelope, Signal, Subject
from app.pipeline.observe import count
from app.pipeline.readers import read_message, read_raw

# Config
KIND_FOR_SOURCE = {"upload": "document_arrived"}  # everything else is a customer_message
MONEY_PATTERN = re.compile(r"LKR ([\d,]+)")
PAYMENT_REF_PATTERN = re.compile(r"\bpay_[A-Za-z]+_\d{8}_\d{4}\b")
DATE_PATTERN = re.compile(r"\bon (\d{1,2} [A-Z][a-z]+ \d{4})")
INJECTION_PATTERN = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|rules)|disregard (?:the |your )?(?:policy|rules|instructions)"
    r"|you are now|system prompt|act as (?:an? )?(?:admin|administrator|system)",
    re.IGNORECASE,
)
UNSAFE_FILENAME = re.compile(r"[^\w.-]")
SCRIPT_RANGES = {"si": (0x0D80, 0x0DFF), "ta": (0x0B80, 0x0BFF)}  # Sinhala and Tamil letters


# --- Understanding the text

def detect_language(text: str) -> str:
    """Sinhala or Tamil when their letters are a fair share of the text, else English."""
    letters = [char for char in text if char.isalpha()] or [" "]
    for language, (low, high) in SCRIPT_RANGES.items():
        if sum(1 for char in letters if low <= ord(char) <= high) / len(letters) > 0.3:
            return language
    return "en"


def find_entities(text: str) -> list[Entity]:
    """The money, payment reference and purchase date that S3 and S6 need."""
    money = [Entity(type="money", value_or_token=f"LKR {raw.replace(',', '')}", confidence=0.9) for raw in MONEY_PATTERN.findall(text)]
    refs = [Entity(type="payment_ref", value_or_token=ref, confidence=0.95) for ref in PAYMENT_REF_PATTERN.findall(text)]
    dates = [Entity(type="purchase_date", value_or_token=datetime.strptime(day, "%d %B %Y").date().isoformat(), confidence=0.9) for day in DATE_PATTERN.findall(text)]
    return money + refs + dates


def save_attachments(object_store, raw_uri: str, external_id: str, attachments: list) -> list[Attachment]:
    """Store each attachment next to the raw body: brain/{tenant}/attachments/{external_id}/{file}."""
    base = raw_uri.split("/raw/")[0]
    saved = []
    for filename, mime, data in attachments:
        safe_name = UNSAFE_FILENAME.sub("_", filename)
        uri = f"{base}/attachments/{external_id}/{safe_name}"
        object_store[uri] = data
        saved.append(Attachment(object_uri=uri, mime=mime, sha256=hashlib.sha256(data).hexdigest()))
    return saved


def choose_actor_and_subject(message: dict, entities: list[Entity], tenant_id: str) -> tuple[Actor, Subject]:
    """A payment is the most useful subject; without one, the customer or uploader is."""
    if "uploaded_by" in message:
        actor = Actor(type="human", ref=message["uploaded_by"])
    elif not message["email"] and message.get("customer_ref"):
        actor = Actor(type="customer", ref=message["customer_ref"])  # the site's own customer id, not personal data
    else:
        actor = Actor(type="customer", ref=pii.make_token(tenant_id, message["email"]))
    refs = [entity.value_or_token for entity in entities if entity.type == "payment_ref"]
    subject = Subject(entity_type="payment", entity_ref=refs[0]) if refs else Subject(entity_type=actor.type, entity_ref=actor.ref)
    return actor, subject


# --- S2 Normalize

def build_signal(k1: RawSignalEnvelope, raw_event_id: str, tenant_id: str, object_store, vault, new_id, dedup_key: str) -> Signal:
    """Read, mask, understand and describe one raw signal as K2."""
    # Step 1: read the message and mask every personal value
    message = read_message(k1, read_raw(object_store, k1.raw_object_uri))
    found = pii.find_personal(message["text"], message["name"], message["email"])
    text_masked, tokens = pii.mask_text(message["text"], found, tenant_id, vault)

    # Step 2: understand it, on masked text only
    entities = find_entities(text_masked)
    actor, subject = choose_actor_and_subject(message, entities, tenant_id)
    flags = ["possible_prompt_injection"] if INJECTION_PATTERN.search(message["text"]) else []
    return Signal(
        signal_id=new_id("sig"), raw_event_id=raw_event_id, kind=KIND_FOR_SOURCE.get(k1.source_type, "customer_message"),
        channel=k1.source_type, actor=actor, subject=subject, text_masked=text_masked,
        language=detect_language(message["text"]), entities=entities, pii_tokens=tokens, flags=flags,
        attachments=save_attachments(object_store, k1.raw_object_uri, k1.external_id, message["attachments"]),
        sensitivity=pii.sensitivity_for(found), dedup_key=dedup_key, thread_ref=thread_of(k1),
    )


def thread_of(k1: RawSignalEnvelope) -> str | None:
    """A chat message's conversation, from the session header S1 kept."""
    session = k1.headers_subset.get("session")
    return f"{k1.connector_id}:{session}" if k1.source_type == "chat" and session else None


def claim(seen_keys, key: str) -> bool:
    """Atomic on Valkey, so two workers never both proceed. A plain set is single threaded, so check then add is safe."""
    if hasattr(seen_keys, "claim"):
        return seen_keys.claim(key)
    if key in seen_keys:
        return False
    seen_keys.add(key)
    return True


def normalize(k1: RawSignalEnvelope, raw_event_id: str, tenant_id: str, object_store, vault, seen_keys, new_id) -> Signal | None:
    """S2: K1 to a masked K2, or None when this signal is a duplicate."""
    # Step 1: claim the dedup key; a redelivery or a second worker stops here
    dedup_key = f"{tenant_id}:{k1.source_type}:{k1.external_id}"
    if not claim(seen_keys, dedup_key):
        count("s2.duplicate")
        return None

    # Step 2: build the signal; on failure release the claim so a retry or replay can run
    try:
        signal = build_signal(k1, raw_event_id, tenant_id, object_store, vault, new_id, dedup_key)
    except Exception:
        seen_keys.discard(dedup_key)
        count(f"s2.failed.{k1.connector_id}")
        raise
    count(f"s2.normalized.{k1.connector_id}")
    return signal
