# pack_schemas.py: the shape of every file in an experiment pack (spec section 5), per pack kind. A pack is a zip with a
# manifest, documents with front matter, a main file of queries or tasks, gold answers, and the kind's extra files.
# Used by: research/packs.py, research/pack_audits.py. Uses: research/contracts.py (PackKind).
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.research.contracts import PackKind

# Config
Sensitivity = Literal["public", "internal", "confidential", "restricted"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a misspelled field is an error, never quietly dropped


class ExposureCheck(Strict):
    checked_on: str
    query: str
    exact_matches: int


class Manifest(Strict):
    kind: PackKind
    name: str = Field(pattern=r"^[a-z0-9_]+$")
    version: str
    company: str
    timezone: str
    currency: str
    created_by: str
    license: str
    files: list[str]
    exposure_check: ExposureCheck | None = None  # the pretraining exposure audit reads it
    notes: str = ""


class DocumentMeta(Strict):
    doc_id: str
    title: str
    domain: str
    sensitivity: Sensitivity
    valid_from: str
    valid_to: str | None = None
    recorded_at: str | None = None
    supersedes: list[str] = []  # documents this one updates, wholly or in part (facts.jsonl names the exact sentence)
    entity_ids: list[str] = []


# --- freshness

class FreshnessQuery(Strict):
    query_id: str
    text: str
    as_of: str
    fact_id: str | None = None
    kind: Literal["stale_sensitive", "control", "canary"]
    paraphrase_of: str | None = None


class FreshnessGold(Strict):
    query_id: str
    expected_value: str
    superseded_values: list[str] = []
    tolerance: float = 0.0  # for numbers: how far an answer may be from the expected value


class Fact(Strict):
    fact_id: str
    subject: str
    unit: str = ""
    old_value: str | None = None  # None for a canary: one value, never superseded
    new_value: str
    old_doc_id: str | None = None
    new_doc_id: str
    old_sentence: str | None = None
    new_sentence: str
    change_at: str | None = None


# --- policy_drift

class DriftTask(Strict):
    task_id: str
    as_of: str
    user_message: str
    initial_state: dict
    expected_actions: list[dict]
    policy_ids: list[str]


class DriftPoint(Strict):
    policy_id: str
    change_at_case_index: int
    change_at_time: str
    type: Literal["sudden", "gradual"]


class PolicyVersion(Strict):
    policy_id: str
    version: int
    valid_from: str
    valid_to: str | None = None
    statement: str
    params: dict = {}


# --- skills

class SkillTask(Strict):
    task_id: str
    user_message: str
    initial_state: dict
    expected_final_state: dict


# --- security

class SecurityTask(Strict):
    task_id: str
    principal: str
    on_behalf_of: str | None = None
    user_message: str
    allowed_actions: list[str]
    forbidden_actions: list[str]
    canary_tokens: list[str] = []


class Principal(Strict):
    principal_id: str
    kind: Literal["human", "agent"]
    tier: str
    roles: list[str] = []
    capabilities: list[str] = []


class Relation(Strict):
    object: str
    relation: str
    subject: str


class Attribute(Strict):
    entity: str
    name: str
    value: str | int | float | bool


class Attack(Strict):
    attack_id: str
    carrier: Literal["document", "tool_output", "chat"]
    payload: str
    target_forbidden_action: str


class IntegrationTask(BaseModel):
    model_config = ConfigDict(extra="allow")  # joins fields from the other kinds by task_id
    task_id: str
    user_message: str


class GoldFinal(Strict):
    task_id: str
    expected: dict = {}


# --- What each kind holds: main file, gold file and extra JSONL files, each with its line model

KINDS: dict[str, dict] = {
    "freshness": {"main": ("queries.jsonl", FreshnessQuery), "gold": ("gold.jsonl", FreshnessGold), "extra": {"facts.jsonl": Fact}},
    "policy_drift": {"main": ("tasks.jsonl", DriftTask), "gold": ("gold.jsonl", GoldFinal),
                     "extra": {"policies.jsonl": PolicyVersion, "drift_points.jsonl": DriftPoint}, "logs": ("event_log.csv", "event_log.xes")},
    "skills": {"main": ("tasks.jsonl", SkillTask), "gold": ("gold.jsonl", GoldFinal), "extra": {}, "logs": ("train_log.xes", "heldout_log.xes")},
    "security": {"main": ("tasks.jsonl", SecurityTask), "gold": ("gold.jsonl", GoldFinal),
                 "extra": {"principals.jsonl": Principal, "relations.jsonl": Relation, "attributes.jsonl": Attribute, "attacks.jsonl": Attack}},
    "integration": {"main": ("tasks.jsonl", IntegrationTask), "gold": ("gold.jsonl", GoldFinal), "extra": {}},
}


def row_id(row: BaseModel) -> str:
    """A query's or a task's id, whichever the line carries."""
    return getattr(row, "query_id", None) or getattr(row, "task_id")
