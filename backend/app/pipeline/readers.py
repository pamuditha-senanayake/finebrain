# readers.py: reads the raw body S1 stored, as email (MIME), web chat (JSON) or an upload.
# Used by: stages_normalize.py. Uses: retry.py, contracts_signal.py.
import email
import json
from email import policy
from email.utils import parseaddr

from app.pipeline.contracts_signal import RawSignalEnvelope
from app.pipeline.retry import call_with_retry

# Config
READ_ATTEMPTS = 3  # the raw object may not be readable for a moment after S1 stores it


class ParseError(Exception):
    """The body cannot be read as its content type. Retrying will not help."""
    retryable = False


class RawUnavailable(Exception):
    """The raw object could not be read after retries. A replay later may work."""
    retryable = True


# --- Reading the raw body

def read_raw(object_store, uri: str) -> str:
    """Read the body S1 stored, retrying briefly when the store hiccups."""
    try:
        body = call_with_retry(lambda: object_store[uri], lambda error: True, attempts=READ_ATTEMPTS, base_delay=0.1)
    except Exception as error:
        raise RawUnavailable(f"{type(error).__name__} reading {uri}") from None
    return body.decode("utf-8")


def read_email(body: str) -> dict:
    """Sender, plain text and attachments from a MIME email."""
    message = email.message_from_string(body, policy=policy.default)
    name, address = parseaddr(str(message.get("From", "")))
    if not address:
        raise ParseError("email has no sender")
    text_part = message.get_body(preferencelist=("plain",))
    attachments = [(part.get_filename() or "attachment", part.get_content_type(), part.get_payload(decode=True) or b"") for part in message.iter_attachments()]
    return {"name": name, "email": address, "text": part_text(text_part) if text_part else "", "attachments": attachments}


def part_text(part) -> str:
    """Text of a part. Many senders skip the charset header; then the body is already text, so read it as is."""
    plain_encoding = part.get("Content-Transfer-Encoding", "7bit").lower() in ("7bit", "8bit")
    if part.get_content_charset() is None and plain_encoding:
        return part.get_payload()
    return part.get_content()


def read_chat(body: str) -> dict:
    """Visitor and text from a web chat message."""
    try:
        chat = json.loads(body)
        return {"name": chat["visitor_name"], "email": chat["visitor_email"], "text": chat["text"], "attachments": []}
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ParseError(f"chat body is not a chat message: {type(error).__name__}") from None


def read_message(k1: RawSignalEnvelope, body: str) -> dict:
    """Pick the reader by source. Uploads have no customer, only the staff member who uploaded."""
    if k1.source_type == "upload":
        return {"name": "", "email": "", "text": body, "attachments": [], "uploaded_by": k1.headers_subset.get("uploaded_by", "unknown")}
    if k1.content_type == "application/json":
        return read_chat(body)
    return read_email(body)
