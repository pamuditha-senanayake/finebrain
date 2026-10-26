# pii.py: finding and masking personal data: patterns, the Luhn card check, tokens and sensitivity.
# Used by: stages_normalize.py. Uses: nothing local.
import hashlib
import re

# Config
EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+\.[\w.]+")  # start only where a run starts: else a long run without @ is retried from every char
PHONE_PATTERN = re.compile(r"\+94[\d ]{9,12}\d|\b0\d{2}[ -]?\d{3}[ -]?\d{4}\b")  # +94 77 123 4567 or 077 123 4567
NIC_PATTERN = re.compile(r"\b(?:\d{12}|\d{9}[VvXx])\b")  # new 12 digit, or old 9 digits plus V or X
CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
ADDRESS_PATTERN = re.compile(
    r"\bNo\.?\s?\d+[A-Za-z]?(?:/\d+)?,?\s+(?:[A-Z][a-z]+\s)+(?:Road|Street|Lane|Mawatha|Avenue|Place),?\s+[A-Z][a-z]+(?:\s\d{1,2})?"
)
RESTRICTED_KINDS = {"nic", "card"}  # these make the whole signal restricted
MIN_NAME_LENGTH = 3


def make_token(tenant_id: str, value: str) -> str:
    """Same value gives the same token, so the vault and dedup stay stable."""
    return "pii_tok_" + hashlib.sha256(f"{tenant_id}:{value}".encode()).hexdigest()[:22]


def passes_luhn(digits: str) -> bool:
    """Real card numbers pass this check; most random digit runs do not."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def find_cards(text: str) -> list[str]:
    """Card-like digit runs that pass Luhn, as written in the text."""
    runs = [match.group() for match in CARD_CANDIDATE.finditer(text)]
    return [run for run in runs if passes_luhn(re.sub(r"\D", "", run))]


def find_personal(text: str, sender_name: str, sender_email: str) -> list[tuple[str, str]]:
    """Every (kind, value) to mask, sender first. The sender is always tokenized, even if absent from the text."""
    found = [("name", sender_name), ("email", sender_email)]
    found += [("email", value) for value in EMAIL_PATTERN.findall(text)]
    found += [("nic", value) for value in NIC_PATTERN.findall(text)]
    found += [("card", value) for value in find_cards(text)]
    found += [("phone", value) for value in PHONE_PATTERN.findall(text)]
    found += [("address", value) for value in ADDRESS_PATTERN.findall(text)]
    first_name = sender_name.split(" ")[0] if sender_name else ""
    if len(first_name) >= MIN_NAME_LENGTH and re.search(rf"\b{re.escape(first_name)}\b", text.replace(sender_name, "")):
        found.append(("first_name", first_name))  # "Thanks, Nimal" without the surname
    unique = dict.fromkeys((kind, value) for kind, value in found if value)
    return list(unique)


def mask_text(text: str, found: list[tuple[str, str]], tenant_id: str, vault) -> tuple[str, list[str]]:
    """Swap each value for its token, longest first so 'Nimal Perera' goes before 'Nimal'."""
    tokens = []
    for _, value in found:
        token = make_token(tenant_id, value)
        vault[token] = value
        tokens.append(token)
    for _, value in sorted(found, key=lambda pair: len(pair[1]), reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(value)}(?!\w)", make_token(tenant_id, value), text)
    return " ".join(text.split()), list(dict.fromkeys(tokens))


def sensitivity_for(found: list[tuple[str, str]]) -> str:
    """An ID or card number makes the signal restricted; anything else personal is confidential."""
    return "restricted" if RESTRICTED_KINDS & {kind for kind, _ in found} else "confidential"
