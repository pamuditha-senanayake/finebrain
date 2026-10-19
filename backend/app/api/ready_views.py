# ready_views.py: step 16, readiness for the console (sample data, shapes from contracts/entity.ts): obligations and how ready they are,
# gaps, evidence requests (S15's check runs first when over an hour old, and tells the DRI of new ones), rules and risks.
# Used by: lists.py, overview_views.py, tests. Uses: readiness_*.py, stages_ready.py, ready_notices.py.

from app.api import ui_models_graph as g
from app.api.ready_notices import fresh
from app.pipeline import readiness_facts, readiness_model, readiness_time, stages_ready
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


class GapTarget(g.UiModel):
    kind: str
    id: str
    label: str


class ReadinessGap(g.UiModel):
    id: str
    target: GapTarget
    missing: str
    due_at: str
    action: str
    dri: str
    escalation_days: list[int]
    request_id: str | None


class EvidenceRequest(g.UiModel):
    id: str
    tenant_id: str
    obligation_id: str
    evidence_key: str
    item: str
    requested_from: str
    status: str
    due_at: str
    created_at: str
    escalation_level: int
    suggested_grant: dict | None
    fulfilled_by: dict | None


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


def obligation_view(lane, instance: Instance) -> dict:
    ob = instance.obligation
    proven, ready, status = readiness_facts.readiness_of(lane, instance, lane.now)
    return Obligation(id=instance.instance_id, tenant_id=lane.seed["tenant_id"], cluster_id=lane.seed["cluster_id"], title=ob.title + readiness_model.period_label(instance.period),
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


# --- The check, its gaps and requests (slice 2)

def gaps_view(lane) -> list[dict]:
    """Every item not proven yet, with its owner and the request asking for it."""
    fresh(lane)
    asked = {r["request_id"] for r in lane.records.list_kind(stages_ready.REQUEST_KIND)}
    return [ReadinessGap(id=readiness_model.gap_id_of(i.instance_id, item.key), target=GapTarget(kind="obligation", id=i.instance_id, label=i.obligation.title + readiness_model.period_label(i.period)),
                         missing=item.label, due_at=i.due_at.isoformat(), action=stages_ready.action_of(lane, item), dri=i.obligation.dri, escalation_days=readiness_time.ESCALATION_DAYS,
                         request_id=rid if (rid := readiness_model.request_id_of(i.instance_id, item.key)) in asked else None).ui() for i, item in stages_ready.gaps(lane, lane.now)]


def shown_grant(request: dict) -> dict | None:
    g = request.get("suggested_grant")
    return {"source": g["source"], "scope": g["scope"], "retentionDays": g["retention_days"], "agents": g["agents"], "revoke": g["revoke"]} if g else None


def requests_view(lane) -> list[dict]:
    """The evidence requests, newest first, with how far each has escalated."""
    fresh(lane)
    stored = sorted(lane.records.list_kind(stages_ready.REQUEST_KIND), key=lambda r: str(r["created_at"]), reverse=True)
    return [EvidenceRequest(id=r["request_id"], tenant_id=lane.seed["tenant_id"], obligation_id=r["instance_id"], evidence_key=r["evidence_key"], item=r["item"],
                            requested_from=r["requested_from"], status=r["status"], due_at=str(r["due_at"]), created_at=str(r["created_at"]), suggested_grant=shown_grant(r),
                            escalation_level=readiness_time.escalation_level(readiness_time.deadline_of(r), lane.now) if r["status"] == "open" else 0,
                            fulfilled_by={"kind": "upload", "ref": r["fulfilled_by"]} if r.get("fulfilled_by") else None).ui() for r in stored]
