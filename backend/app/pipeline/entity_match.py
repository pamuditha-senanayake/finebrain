# entity_match.py: step 13a, entity matching at S2. Turns a masked signal into the real things it is about (one id per
# thing, so the same customer twice is one entity) and the typed links between them. No model call: only exact keys.
# Step 14 adds things a document names (a supplier, a contract), keyed by their name in a plain form.
# Used by: orchestrate.py (S2), stages_extract.py (S11), demos/entities_demo.py, tests. Uses: contracts_signal.py, a registry (store_entities.py).
import hashlib
import re
from datetime import datetime

from app.pipeline.contracts_signal import Signal

# Config
ENTITY_TYPES = ("organization", "customer", "payment", "document", "contract", "product")
EXACT_KEYS = {"customer": re.compile(r"pii_tok_[0-9a-f]{22}"), "payment": re.compile(r"pay_[A-Za-z]+_\d{8}_\d{4}")}  # the keys S2 matches
COMPANY_ENDINGS = re.compile(r"\b(?:pvt|private|ltd|limited|plc|inc|llc|co)\b")  # "Lanka Print (Pvt) Ltd" and "Lanka Print" are one supplier
LINK_TYPES = {"paid_with": ("customer", "payment"), "mentions": ("document", None)}  # None: any type
SEED_SOURCE = "seed"


def entity_id_of(entity_type: str, key: str) -> str:
    """Same type and key give the same id, so every worker agrees without asking the store."""
    return f"ent_{entity_type}_{hashlib.sha256(f'{entity_type}:{key}'.encode()).hexdigest()[:12]}"


def document_source(tenant_id: str, document_id: str) -> str:
    """The source id S2 gives an upload: its dedup key."""
    return f"{tenant_id}:upload:{document_id}"


# --- Matching

def things_in(signal: Signal) -> list[tuple[str, str]]:
    """(type, key) for each real thing: the customer who wrote, payments named, and the document itself.
    Customers are keyed by their masked token, so the registry never holds a name or an address."""
    found = []
    if signal.actor.type == "customer":
        found.append(("customer", signal.actor.ref))
    found += [("payment", entity.value_or_token) for entity in signal.entities if entity.type == "payment_ref"]
    if signal.kind == "document_arrived":
        found.append(("document", signal.dedup_key.rsplit(":", 1)[-1]))
    return list(dict.fromkeys(found))


def links_in(things: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Typed links between things found together: a customer paid with each payment; a document mentions the rest."""
    links = []
    for rel, (from_type, to_type) in LINK_TYPES.items():
        sources = [thing for thing in things if thing[0] == from_type]
        targets = [thing for thing in things if thing[0] != from_type and (to_type is None or thing[0] == to_type)]
        links += [(entity_id_of(*a), rel, entity_id_of(*b)) for a in sources for b in targets]
    return links


# --- Recording

def record_entities(store, signal: Signal, now: datetime) -> list[str]:
    """Note each thing and link under this signal's dedup key, and return the entity ids. Safe to run twice."""
    things = things_in(signal)
    for entity_type, key in things:
        store.note(entity_id_of(entity_type, key), entity_type, key, signal.dedup_key, now)
    for from_id, rel, to_id in links_in(things):
        store.link(from_id, rel, to_id, signal.dedup_key, now)
    return [entity_id_of(*thing) for thing in things]


def name_key(entity_type: str, name: str) -> str:
    """A name in a plain form: lower case, no punctuation, and no company ending for an organization. Customers and payments
    keep their exact key (a masked token, a payment reference), so they meet the ones S2 matched."""
    if entity_type in ("customer", "payment"):
        return name.strip()
    plain = re.sub(r"[^a-z0-9]+", " ", name.lower())
    plain = COMPANY_ENDINGS.sub(" ", plain) if entity_type == "organization" else plain
    return " ".join(plain.split())


def note_named(store, entity_type: str, name: str, source_id: str, now: datetime) -> str | None:
    """Note a thing a document names, and return its id. None when the name is empty once made plain."""
    if entity_type not in ENTITY_TYPES:
        return None
    if entity_type in EXACT_KEYS and not EXACT_KEYS[entity_type].fullmatch(name.strip()):
        return None  # "monthly fee" is not a payment: only a payment reference or a masked customer token is
    key = name_key(entity_type, name)
    if not key:
        return None
    entity_id = entity_id_of(entity_type, key)
    store.note(entity_id, entity_type, key, source_id, now)
    return entity_id


def seed_known(store, seed: dict, now: datetime) -> None:
    """Things the brain knows before any signal: the company itself."""
    tenant_id = seed["tenant_id"]
    store.note(entity_id_of("organization", tenant_id), "organization", tenant_id, SEED_SOURCE, now)
