# ui_models_graph.py: Pydantic copies of the console's graph shapes (org.ts Agent; knowledge.ts Skill, Policy,
# ResolverRule, Graph), the 9c screens. Used by: graph_views.py, graph_map.py. Uses: ui_models.py (UiModel, VersionRef, Tier).
from typing import Literal

from app.api.ui_models import Tier, UiModel, VersionRef

Sensitivity = Literal["public", "internal", "confidential", "restricted"]
NodeType = Literal["skill", "policy", "security", "sensor", "template", "fact", "document", "agent", "tool"]


class Agent(UiModel):
    id: str
    tenant_id: str
    name: str
    kind: Literal["worker", "supervisor"]
    tier: Tier
    cluster_id: str
    description: str
    autonomy: Literal["trainee", "supervised", "autonomous"]
    skills: list[VersionRef]
    capabilities: list[str]
    access_level: Sensitivity
    sensors: list[str]
    templates: list[str]
    policies: list[str]
    status: Literal["idle", "working", "blocked", "error", "paused"]
    work_kind: Literal["retrieval", "judgment", "tool"] | None
    dri: str
    queue_depth: int
    throughput_per_hour: float
    error_rate: float
    cost_today_usd: float
    task_success: float
    training: list[dict]


class SkillStep(UiModel):
    id: str
    kind: Literal["judgment", "tool", "retrieval", "quality_gate"]
    text: str
    tool: str | None


class Skill(UiModel):
    id: str
    tenant_id: str
    name: str
    version: int
    branch: str
    status: Literal["draft", "active", "deprecated"]
    cluster_id: str
    trigger: str
    inputs: list[str]
    steps: list[SkillStep]
    tools: list[str]
    policies: list[str]
    required_capabilities: list[str]
    outputs: list[str]
    template_fields: list[str]
    eval_suite: dict
    health: dict
    agent_ids: list[str]
    dri: str
    updated_at: str
    origin: Literal["authored", "skillify", "overnight"]


class Policy(UiModel):
    id: str
    key: str
    tenant_id: str
    name: str
    version: int
    branch: str
    cluster_id: str
    statement: str
    rule: dict
    criticality: int
    valid_from: str
    valid_to: str | None
    recorded_at: str
    superseded_by: str | None
    evidence: list[str]
    freshness: dict
    dependents: list[dict]
    dri: str


class ResolverRule(UiModel):
    id: str
    tenant_id: str
    event: str
    match: str
    skill: VersionRef
    agent_id: str
    priority: int
    trigger_eval: dict


class GraphNode(UiModel):
    id: str
    type: NodeType
    label: str
    ref_id: str
    cluster_id: str
    sensitivity: Sensitivity
    requires: dict
    x: float
    y: float


class GraphEdge(UiModel):
    id: str
    source: str
    target: str
    kind: Literal["uses", "governs", "feeds", "fills", "depends", "grants", "evidences"]
    requires_capability: str | None


class Graph(UiModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
