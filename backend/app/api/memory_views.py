# memory_views.py: the Living memory page's answers from the live stores (stage 7), in the shapes of
# frontend/contracts/memory.ts: the map, one area, the trace list and one trace, drift, and skills from traces.
# Counts come from indexed queries, a trace page from a keyset cursor, and flagged lists from the flags and reviews
# that name their traces, never from listing every trace. Used by: routes.py (GET memory...), memory_fixes.py (the
# actions), tests/test_memory_views.py, scripts/memory_contract_fixture.py. Uses: ui_models_memory.py, views.py (run steps),
# stages_memory_drift.py (week series), stages_memory_tidy.py (cold traces), stages_memory_flow.py (records kinds).
from datetime import timedelta

from app.api import ui_models_memory as ui
from app.api import views
from app.api.ui_models_work import TraceStep
from app.pipeline import stages_memory_drift as drift
from app.pipeline import stages_memory_flow as flow
from app.pipeline import stages_memory_tidy as tidy
from app.pipeline.contracts_memory import DriftFlag, TraceRecord
from app.pipeline.store_patterns import PATTERN_BUDGET
from app.pipeline.store_traces import PAGE_SIZE

# Config
AREA_NAMES = {"customer_care": "Customers", "finance": "Money", "legal": "Rules", "people": "Staff", "operations": "Operations",
              "sales": "Sales", "product": "Product", "general": "Other"}
CLOSED_KIND = "memory_review_closed"  # records kind keyed by trace id: a surprise a person has answered
OPEN_STATES = ("detected", "sent_to_l1", "awaiting_approval", "approved")
METRIC_LABEL = {"skill": "Runs that follow the skill", "policy": "Work outside the policy per week", "security": "Actions without an allow"}
LIST_CAP = 500  # a flagged list reads at most this many traces


# --- Surprises and drift, read from what names them

def open_surprises(lane, area: str | None = None) -> list[dict]:
    """Surprises waiting for a person: review records with no answer yet. Read by kind, never by listing traces."""
    return [r for r in lane.records.list_kind(flow.REVIEW_KIND) if (area is None or r["area"] == area) and not lane.records.load(CLOSED_KIND, r["trace_id"])]


def open_flags(lane, area: str | None = None) -> list[DriftFlag]:
    flags = [f for state in OPEN_STATES for f in lane.drift.in_state(state)]
    return [f for f in flags if area is None or f.area == area]


def drift_by_trace(lane) -> dict[str, list[str]]:
    kinds: dict[str, list[str]] = {}
    for flag in open_flags(lane):
        for trace_id in flag.evidence_trace_ids:
            kinds.setdefault(trace_id, []).append(flag.kind)
    return kinds


# --- The map and its areas

def area_view(lane, key: str) -> ui.MemoryArea:
    week_ago = lane.now - timedelta(days=7)
    patterns = lane.patterns.area_patterns(key).values()
    flags = open_flags(lane, key)
    drafts = [d for d in lane.records.list_kind(drift.DRAFT_KIND) if d["area"] == key]
    return ui.MemoryArea(
        key=key, name=AREA_NAMES[key], enabled=lane.patterns.area_on(key), traces7d=lane.traces.count(key, week_ago), traces_total=lane.traces.count(key),
        patterns=len(patterns), pattern_budget=PATTERN_BUDGET,
        skills=ui.AreaSkills(authored=len({p.key.split("|")[1] for p in patterns} - {"none"}), from_traces=len(drafts)),
        drift=ui.DriftCounts(**{kind: sum(f.kind == kind for f in flags) for kind in ("skill", "policy", "security")}),
        surprises=len(open_surprises(lane, key)), outside_policy=lane.traces.count(key, week_ago, "outside"))


def memory_map(lane) -> ui.MemoryMap:
    areas = [area_view(lane, key) for key in AREA_NAMES]
    totals = ui.MapTotals(traces7d=sum(a.traces7d for a in areas), patterns=sum(a.patterns for a in areas), surprises=sum(a.surprises for a in areas),
                          drift=ui.DriftCounts(**{kind: sum(getattr(a.drift, kind) for a in areas) for kind in ("skill", "policy", "security")}))
    return ui.MemoryMap(tenant_id=lane.seed["tenant_id"], as_of=lane.now.isoformat(), is_sample=False, areas=areas, totals=totals)


def pattern_view(lane, key: str, pattern, total: int) -> ui.Pattern:
    _, skill, _, outcome, check = pattern.key.split("|")
    name = f"{skill if skill != 'none' else 'No skill'} · {outcome}" + (", outside policy" if check == "outside" else "")
    weeks = [week[pattern.pattern_id] for week in drift.week_series(lane, [pattern.pattern_id])]
    return ui.Pattern(id=pattern.pattern_id, area=key, name=name, steps=pattern.steps, outcome=outcome, policy_check=check, skill_id=None if skill == "none" else skill,
                      week_counts=weeks, share=round(pattern.count / max(1, total), 2), example_trace_ids=pattern.examples[:5])


def drift_view(flag: DriftFlag) -> ui.DriftItem:
    return ui.DriftItem(
        id=flag.flag_id, kind=flag.kind, area=flag.area, subject=ui.DriftSubject(**flag.subject.model_dump()), summary=flag.summary,
        metric=ui.DriftMetric(label=METRIC_LABEL[flag.kind], usual=flag.usual, latest=flag.latest), evidence_trace_ids=flag.evidence_trace_ids, state=flag.state,
        fix=ui.DriftFix(summary=flag.fix.summary, change_request_id=flag.fix.change_request_id) if flag.fix else None,
        recheck=ui.DriftRecheck(until=flag.recheck.until.isoformat(), result=flag.recheck.result) if flag.recheck else None,
        reopened_note=flag.reopened_note, raised_at=flag.raised_at.isoformat())


def area_detail(lane, key: str) -> ui.AreaDetail | None:
    if key not in AREA_NAMES:
        return None
    patterns = sorted(lane.patterns.area_patterns(key).values(), key=lambda p: -p.count)
    total = sum(p.count for p in patterns)
    return ui.AreaDetail(area=area_view(lane, key), patterns=[pattern_view(lane, key, p, total) for p in patterns],
                         drifts=[drift_view(f) for f in open_flags(lane, key)])


# --- Traces

def subject_of(lane, trace: TraceRecord) -> str:
    """What the work was about, in the console's own words for the run; a hand refund names its refund."""
    if trace.source == "outside":
        return f"Refund by hand · {trace.input_ref.removeprefix('shop-')}"
    run = lane.records.load("run", trace.run_id) if trace.run_id else None
    return views.run_view(lane, run).subject if run else trace.input_ref


def summary_view(lane, trace: TraceRecord, drifting: dict[str, list[str]]) -> ui.TraceSummary:
    match = lane.records.load(flow.MATCH_KIND, trace.trace_id) or {}
    return ui.TraceSummary(
        id=trace.trace_id, area=trace.area, source=trace.source, subject=subject_of(lane, trace), started_at=trace.started_at.isoformat(),
        ended_at=trace.ended_at.isoformat() if trace.ended_at else None, outcome=trace.outcome, pattern_id=match.get("pattern_id"),
        match=match.get("match", "normal"), policy_check=trace.policy_check, drift=sorted(set(drifting.get(trace.trace_id, []))), run_id=trace.run_id)


def named_page(lane, trace_ids: list[str], cursor: str | None) -> tuple[list[TraceRecord], str | None, int]:
    """A flagged list: the traces its flags or reviews name, newest first, a page at a time by offset."""
    traces = sorted((t for trace_id in dict.fromkeys(trace_ids[:LIST_CAP]) if (t := lane.traces.get(trace_id))), key=lambda t: (t.started_at, t.trace_id), reverse=True)
    start = int(cursor or 0)
    return traces[start:start + PAGE_SIZE], str(start + PAGE_SIZE) if start + PAGE_SIZE < len(traces) else None, len(traces)


def trace_page(lane, area: str | None, flag: str | None, cursor: str | None) -> ui.TracePage:
    drifting = drift_by_trace(lane)
    if flag == "surprise":
        items, next_cursor, total = named_page(lane, [r["trace_id"] for r in open_surprises(lane, area)], cursor)
    elif flag == "drift":
        items, next_cursor, total = named_page(lane, [t for f in open_flags(lane, area) for t in f.evidence_trace_ids], cursor)
    else:
        check = "outside" if flag == "outside_policy" else None
        items, next_cursor = lane.traces.page(area, cursor, PAGE_SIZE, check)
        total = lane.traces.count(area, None, check)
    return ui.TracePage(items=[summary_view(lane, t, drifting) for t in items], next_cursor=next_cursor, total=total)


def activity_steps(trace: TraceRecord) -> list[TraceStep]:
    """A trace whose run record is gone (or never kept, as with seeded history): its steps by activity, with the why."""
    why = iter(trace.why)
    return [TraceStep(id=f"{trace.trace_id}-s{i}", idx=i, kind="judgment", title=step.replace("_", " ").capitalize(), decision="done", reason=next(why, ""),
                      duration_ms=0, at=trace.started_at.isoformat(), facts=[], access=None, gate=None, tool=None, template_fields=[], cost_tokens=0)
            for i, step in enumerate(trace.steps)]


def hand_steps(trace: TraceRecord) -> list[TraceStep]:
    titles = ["A person refunded by hand in the shop", "Checked against the refund policy in force that day"]
    return [TraceStep(id=f"{trace.trace_id}-s{i}", idx=i, kind="human" if i == 0 else "quality_gate", title=title, decision=trace.outcome if i == 0 else trace.policy_check,
                      reason="" if i == 0 else "; ".join(trace.why), duration_ms=0, at=trace.started_at.isoformat(), facts=[], access=None, gate=None, tool=None,
                      template_fields=[], cost_tokens=0) for i, title in enumerate(titles)]


def trace_detail(lane, trace_id: str) -> ui.TraceDetail | None:
    trace = lane.traces.get(trace_id) or tidy.cold_trace(lane, trace_id)
    if trace is None:
        return None
    run = lane.records.load("run", trace.run_id) if trace.run_id else None
    steps = views.run_detail(lane, run).steps if run else hand_steps(trace) if trace.source == "outside" else activity_steps(trace)
    policies = [ui.TracePolicy(id=p.policy_ref.id, name=p.policy_ref.id, version=p.policy_ref.version, valid_from=p.valid_from.isoformat(),
                               valid_to=p.valid_to.isoformat() if p.valid_to else None) for p in trace.policies]
    access = [ui.TraceAccess(action=a.action, principal=a.principal_id, on_behalf_of=a.on_behalf_of, decision=a.decision, rule_id=a.rule_id, reason=a.reason,
                             latency_ms=a.latency_ms) for a in trace.access]
    skill = ui.SkillRef(id=trace.skill.id, version=trace.skill.version, branch=trace.skill.branch) if trace.skill else None
    return ui.TraceDetail(**summary_view(lane, trace, drift_by_trace(lane)).model_dump(), input_ref=trace.input_ref, steps=steps, policies=policies,
                          skill=skill, access=access, why=trace.why)


# --- Skills from traces

def draft_view(lane, draft: dict) -> ui.ExtractedSkill:
    steps = [ui.DraftStep(activity=step, title=step.replace("_", " ").capitalize()) for step in draft["steps"]]
    name = f"{AREA_NAMES[draft['area']]}: {steps[0].title.lower()} to {steps[-1].title.lower()}" if steps else draft["draft_id"]
    return ui.ExtractedSkill(id=draft["draft_id"], area=draft["area"], name=name, pattern_id=draft["pattern_id"], steps=steps, support=draft["support"],
                             same_outcome_share=draft["same_outcome_share"], follow_rate=draft["follow_rate"], state=draft["state"],
                             change_request_id=draft.get("change_request_id"), created_at=draft.get("created_at") or lane.now.isoformat())


# --- The GET paths

def serve(lane, resource: str, query: dict) -> dict | list | None:
    """GET memory, memory/areas/:key, memory/traces, memory/traces/:id, memory/drifts, memory/skills. None means not found."""
    parts = resource.split("/")
    if resource == "memory":
        return memory_map(lane).ui()
    if parts[1:2] == ["areas"] and len(parts) == 3:
        found = area_detail(lane, parts[2])
        return found.ui() if found else None
    if resource == "memory/traces":
        return trace_page(lane, query.get("area"), query.get("flag"), query.get("cursor")).ui()
    if parts[1:2] == ["traces"] and len(parts) == 3:
        found = trace_detail(lane, parts[2])
        return found.ui() if found else None
    if resource == "memory/drifts":
        return [drift_view(f).ui() for f in open_flags(lane, query.get("area")) if not query.get("kind") or f.kind == query["kind"]]
    if resource == "memory/skills":
        return [draft_view(lane, d).ui() for d in lane.records.list_kind(drift.DRAFT_KIND)]
    return None
