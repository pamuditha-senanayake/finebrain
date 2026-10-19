# ready_views.py: step 16, readiness for the console: each obligation's next instance with how ready it is, the readiness
# rules, and the risk register. Shapes copy contracts/entity.ts (Obligation, ReadinessRule, Risk). All of it is sample data.
# Used by: lists.py (GET obligations, readiness-rules, risks), overview_views.py (counts), tests. Uses: readiness_model.py, readiness_facts.py.
from datetime import datetime

from app.api import ui_models_graph as g
from app.pipeline import readiness_facts, readiness_model
from app.pipeline.readiness_model import Instance


class EvidenceItem(g.UiModel):
    key: str
    label: str
    satisfied_by: str | None


class Obligation(g.UiModel):
    id: str
    tenant_id: str
    cluster_id: str
    title: str
    jurisdiction: str
    category: str
    due_at: str
    prepare_by: str
    required_evidence: list[EvidenceItem]
    readiness: int
    status: str
    dri: str
    is_sample: bool
    note: str


class ReadinessRule(g.UiModel):
    id: str
    target: str
    requires: str
    check_every: str
    escalation_days: list[int]
    last_run_at: str


class Risk(g.UiModel):
    id: str
    title: str
    likelihood: str
    impact: str
    owner: str
    mitigation: str
    linked_obligation: str | None


def period_label(period: str | None) -> str:
    """2026-09 reads as September 2026, 2025 as 2025, and no period as nothing."""
    if not period:
        return ""
    if len(period) == 4:
        return f" · {period}"
    return f" · {datetime.strptime(period, '%Y-%m').strftime('%B %Y')}"


def obligation_view(lane, instance: Instance) -> dict:
    ob = instance.obligation
    proven, ready, status = readiness_facts.readiness_of(lane, instance, lane.now)
    return Obligation(id=instance.instance_id, tenant_id=lane.seed["tenant_id"], cluster_id=lane.seed["cluster_id"], title=ob.title + period_label(instance.period),
                      jurisdiction=ob.jurisdiction, category=ob.category, due_at=instance.due_at.isoformat(), prepare_by=instance.prepare_by.isoformat(),
                      required_evidence=[EvidenceItem(key=item.key, label=item.label, satisfied_by=fact_id) for item, fact_id in proven],
                      readiness=ready, status=status, dri=ob.dri, is_sample=True, note=ob.note).ui()


def obligations_view(lane) -> list[dict]:
    """Every obligation's next instance, soonest first."""
    return [obligation_view(lane, instance) for instance in readiness_model.current(lane, lane.now)]


def rules_view(lane) -> list[dict]:
    """The readiness rules. Readiness is worked out on every read, so each was last run now."""
    rules = lane.seed.get("readiness", {}).get("rules", [])
    return [ReadinessRule(**{**rule, "last_run_at": lane.now.isoformat()}).ui() for rule in rules]


def risks_view(lane) -> list[dict]:
    return [Risk(**risk).ui() for risk in lane.seed.get("readiness", {}).get("risks", [])]
