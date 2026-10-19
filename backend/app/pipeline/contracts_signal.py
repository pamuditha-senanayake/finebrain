# contracts_signal.py: Pydantic models for the intake seams (envelope, shared types, K1, K2, K3, K12).
# Used by: the other contracts_*.py files, scripts/check_golden.py. Uses: nothing local.
# Source of truth: Docs/CB_System_Reference.md section 6.
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Config: enum values and patterns copied from the design doc
Env = Literal["production", "staging", "sandbox"]
Sensitivity = Literal["public", "internal", "confidential", "restricted"]
SourceType = Literal["email", "chat", "webhook", "poll", "upload", "clarity_export", "calendar"]
SignalKind = Literal[
    "customer_message", "billing_event", "document_arrived", "usage_event",
    "calendar_event", "ux_signal", "monitor_alert", "review",
]
PII_TOKEN_PATTERN = r"^pii_tok_[A-Za-z0-9]{22}$"
MAX_RAW_BYTES = 25 * 1024 * 1024  # larger bodies go to the upload path

Criticality = Annotated[int, Field(ge=0, le=4)]
PiiToken = Annotated[str, Field(pattern=PII_TOKEN_PATTERN)]


# --- Shared types (section 5.1)

class VersionRef(BaseModel):
    id: str
    version: int
    branch: str
    commit_id: str


class Money(BaseModel):
    """Amount in minor units, so LKR 85,000.00 is 8500000."""
    amount_minor: int = Field(strict=True)  # strict rejects floats
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Principal(BaseModel):
    type: Literal["agent", "human"]
    id: str
    capabilities: list[str]
    tier: str


class Touches(BaseModel):
    money: bool
    personal_data: bool
    public_content: bool
    legal_tax: bool
    clusters: list[str]


class Subject(BaseModel):
    entity_type: str
    entity_ref: str


# --- Shared envelope for every queue message (section 5.0)

class Envelope(BaseModel):
    event_id: str  # UUIDv7 string, consumers dedupe on it
    event_type: str
    schema_version: int
    tenant_id: str
    cluster_id: str
    env: Env
    branch: str
    occurred_at: datetime
    recorded_at: datetime
    trace_id: str
    correlation_id: str
    causation_id: str | None = None
    producer: str
    payload: dict  # one of the contracts below, validated by the consumer


# --- K1 RawSignalEnvelope (S1 to S2, topic signals.raw)

class RawSignalEnvelope(BaseModel):
    connector_id: str
    grant_id: str
    source_type: SourceType
    external_id: str
    received_at: datetime
    signature_verified: Literal[True]  # unverified signals never get published
    raw_object_uri: str
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: str
    size_bytes: int = Field(ge=0, le=MAX_RAW_BYTES)
    headers_subset: dict[str, str] = {}


# --- K2 Signal (S2 to S3 and S11, topic signals.normalized)

class Actor(BaseModel):
    type: Literal["customer", "human", "system"]
    ref: str  # a PiiToken for people, an id for systems


class Entity(BaseModel):
    type: str
    value_or_token: str
    confidence: float = Field(ge=0, le=1)


class Attachment(BaseModel):
    object_uri: str
    mime: str
    sha256: str


class Signal(BaseModel):
    signal_id: str
    raw_event_id: str
    kind: SignalKind
    channel: str
    actor: Actor
    subject: Subject
    text_masked: str | None = None
    language: str | None = None
    entities: list[Entity] = []
    attachments: list[Attachment] = []
    pii_tokens: list[PiiToken]
    sensitivity: Sensitivity
    dedup_key: str
    flags: list[str] = []  # added in S2 step 7, e.g. possible_prompt_injection; optional so old messages validate
    entity_ids: list[str] = []  # added in step 13a: the registry ids of the real things it is about; optional so old messages validate
    domain: str | None = None  # added in step 13a: one of item_tags.DOMAINS; None on messages from before it


# --- K3 TaskRequest (S3 to S4, topic tasks.created)

class TaskRequest(BaseModel):
    task_id: str
    signal_ids: list[str] = Field(min_length=1)
    activity_id: str
    skill_ref: VersionRef  # pinned at route time so a mid run release cannot change it
    agent_id: str
    on_behalf_of: str | None
    resolver_rule_id: str
    match_score: float = Field(ge=0, le=1)
    base_criticality: Criticality
    due_at: datetime
    priority: int = Field(ge=1, le=5)
    flags: list[str] = []  # carried from K2 (e.g. possible_prompt_injection) so S7 can weigh them; optional


# --- K12 FactCandidate (S11 to S12, topic facts.candidates)

class FactValue(BaseModel):
    type: str
    raw: str
    normalized: str


class Evidence(BaseModel):
    document_id: str
    page: int | None
    span: str  # character offsets as "start:end"
    quote_sha256: str


class Extractor(BaseModel):
    model_id: str
    confidence: float = Field(ge=0, le=1)


class FactCandidate(BaseModel):
    candidate_id: str
    statement: str
    subject: Subject
    predicate: str
    value: FactValue
    valid_from: datetime | None
    valid_to: datetime | None
    evidence: Evidence
    extractor: Extractor
    sensitivity: Sensitivity
