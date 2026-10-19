# item_tags.py: step 13a, the four tags. Tenant and time are already on every item; this adds the domain (one of a fixed
# list) and the entity ids, on each signal at S2 and on each chunk wherever one is written.
# Used by: orchestrate.py (S2), stages_file.py (S11), stages_version.py (S5 re-embed), adapters.py (seed chunks), scripts/backfill_tags.py.
# Uses: entity_match.py, stages_normalize.py (payment pattern), observe.py.
import re

from app.pipeline import entity_match
from app.pipeline.contracts_signal import Signal
from app.pipeline.observe import count, log_event
from app.pipeline.stages_normalize import PAYMENT_REF_PATTERN

# Config
# A fixed list, the same for every tenant, so the axis never grows (Docs/CB_Memory_Architecture.md section 1)
DOMAINS = {
    "customer_care": "Customer questions, complaints, refunds, support replies",
    "finance": "Invoices, payments, tax, accounts, budgets",
    "legal": "Contracts, terms, compliance, legal notices",
    "people": "Staff, hiring, payroll, leave, HR policies",
    "operations": "Processes, suppliers, logistics, internal tools",
    "sales": "Leads, deals, pricing, proposals, customers to win",
    "product": "Features, roadmap, releases, product documentation",
    "general": "Anything that fits no other domain, including the company itself",
}
FALLBACK = "general"
TOKEN_PATTERN = re.compile(r"pii_tok_[0-9a-f]{22}")
CLASSIFY_CHARS = 3000  # the start of a document is enough to file it, and keeps the call cheap


def default_domain(seed: dict) -> str:
    """The domain of the cluster this pipeline serves: where its emails and chats, and its seed knowledge, belong."""
    return seed["cluster_id"] if seed.get("cluster_id") in DOMAINS else FALLBACK


def customer_check(entities):
    """A test for masked tokens: only a token the registry knows as a customer becomes an entity tag."""
    return lambda token: entities.get(entity_match.entity_id_of("customer", token)) is not None


# --- Tagging items

def entities_in_text(text: str, is_customer) -> list[str]:
    """Entity ids of the payments and known customers a text names. The document itself is the source, not a tag,
    so a policy with no customer or payment in it stays general and every case in its domain can read it."""
    payments = [entity_match.entity_id_of("payment", ref) for ref in PAYMENT_REF_PATTERN.findall(text)]
    customers = [entity_match.entity_id_of("customer", token) for token in TOKEN_PATTERN.findall(text) if is_customer(token)]
    return list(dict.fromkeys(payments + customers))


def tagged(item: dict, domain: str, is_customer) -> dict:
    """The item with its domain (kept when it already has one) and the entities its text names."""
    return {**item, "domain": item.get("domain") or domain, "entity_ids": entities_in_text(item["text"], is_customer)}


def tagger(seed: dict, entities):
    """A function that tags seed and released knowledge with the pipeline's own domain."""
    domain, is_customer = default_domain(seed), customer_check(entities)
    return lambda item: tagged(item, domain, is_customer)


# --- Tagging signals at S2

def classify(classifier, text: str) -> str:
    """Claude picks a domain from the fixed list. No classifier, no answer, or an outage files it under general."""
    if classifier is None:
        return FALLBACK
    try:
        return classifier(text[:CLASSIFY_CHARS], DOMAINS) or FALLBACK
    except Exception as error:  # a model outage never stops intake; the document is still filed and searchable
        count("s2.domain_unclassified")
        log_event("S2", "domain_unclassified", error=type(error).__name__)
        return FALLBACK


def tag_signal(lane, signal: Signal) -> Signal:
    """S2: record the signal's entities, and set its domain: an upload is classified, a message takes its cluster's."""
    entity_ids = entity_match.record_entities(lane.entities, signal, lane.now)
    if signal.kind == "document_arrived":
        domain = classify(lane.classify, signal.text_masked or "")
    else:
        domain = default_domain(lane.seed)
    return signal.model_copy(update={"entity_ids": entity_ids, "domain": domain})
