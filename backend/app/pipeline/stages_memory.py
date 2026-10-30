# stages_memory.py: the living memory's walking skeleton (stage 4), in memory. One function per seam: a run becomes a
# trace (K16), triage matches it to its area's patterns (K17), the drift checks raise flags (K18), and a steady
# pattern no skill covers becomes a skill draft (K19). Thin on purpose; stage 5 and 6 thicken each one.
# Used by: tests/test_memory_skeleton.py. Uses: contracts_memory.py, contracts_run.py, contracts_reason.py,
# activities.py (step names), stages_spike.py (the spike bar).
import statistics
from dataclasses import dataclass, field
from datetime import datetime

from app.pipeline.activities import activity_of
from app.pipeline.contracts_memory import Area, AreaMatch, DriftFix, DriftFlag, DriftSubject, PolicyCheck, SkillDraft, TraceAccess, TracePolicy, TraceRecord
from app.pipeline.contracts_reason import AccessDecision
from app.pipeline.contracts_run import RunRecord
from app.pipeline.stages_spike import SPIKE_MIN, SPIKE_RATIO

# Config: the starting numbers in Docs/CB_Living_Memory_Architecture.md section 13
PATTERN_BUDGET = 50
EXAMPLES_PER_PATTERN = 5
NEAR_MATCH_STEPS = 1  # a trace one step away from a pattern, with the same skill and ending, still counts as normal
NEAR_SIMILARITY = 0.8
SKILL_DRIFT_BAR = 0.10  # follow rate this far below its usual weeks
DRAFT_MIN_SUPPORT = 20
DRAFT_MIN_SAME_OUTCOME = 0.9


# --- K16: a run becomes a trace

# Escalated means the case needed what the policy did not allow on its own; a failed run never reached the check.
def policy_check_of(run: RunRecord) -> PolicyCheck:
    return {"escalated": "outside", "failed": "unknown"}.get(run.outcome, "within")


def trace_of_run(run: RunRecord, tenant_id: str, area: Area, started_at: datetime, input_ref: str,
                 policies: list[TracePolicy], decisions: list[AccessDecision]) -> TraceRecord:
    """The whole piece of work, start to end: steps by activity, the rules in force, every access decision, the why."""
    steps = [s.activity_id or activity_of(s.kind, s.decision) for s in run.steps]
    access = [TraceAccess(decision_id=d.decision_id, action=d.action or "", principal_id=d.principal_id or "", on_behalf_of=d.on_behalf_of,
                          decision=d.decision, effective_tier=d.effective_tier) for d in decisions if d.run_id == run.run_id]
    return TraceRecord(
        trace_id=f"tr-{run.run_id}", tenant_id=tenant_id, area=area, source="finebrain", started_at=started_at, ended_at=None,
        input_ref=input_ref, steps=steps, policies=policies, skill=run.skill_ref, access=access, outcome=run.outcome,
        decided_by=run.decided_by, why=[s.reason for s in run.steps if s.kind == "judgment" and s.reason],
        policy_check=policy_check_of(run), run_id=run.run_id,
    )


def trace_of_outside(tenant_id: str, event_id: str, area: Area, at: datetime, steps: list[str], outcome: str,
                     policy_check: PolicyCheck, policies: list[TracePolicy]) -> TraceRecord:
    """Work done outside Finebrain, such as a refund made by hand in Stripe, checked against the policy in force that day."""
    return TraceRecord(trace_id=f"tr-{event_id}", tenant_id=tenant_id, area=area, source="outside", started_at=at, ended_at=at,
                       input_ref=event_id, steps=steps, policies=policies, skill=None, access=[], outcome=outcome, decided_by=None,
                       why=[], policy_check=policy_check, run_id=None)


# --- K17: triage against the area's patterns

@dataclass
class Pattern:
    pattern_id: str
    key: str
    steps: list[str]
    count: int = 0
    examples: list[str] = field(default_factory=list)


# Data and the budget rule that guards it belong together, so this one store is a class. Stage 5 moves it to Postgres.
@dataclass
class PatternStore:
    by_area: dict[tuple[str, str], dict[str, Pattern]] = field(default_factory=dict)

    def area(self, tenant_id: str, area: str) -> dict[str, Pattern]:
        return self.by_area.setdefault((tenant_id, area), {})

    def add(self, trace: TraceRecord) -> Pattern | None:
        """A new pattern from a trace a person confirmed; refused once the area is at its budget."""
        patterns = self.area(trace.tenant_id, trace.area)
        if len(patterns) >= PATTERN_BUDGET:
            return None
        pattern = Pattern(pattern_id=f"pt-{trace.area}-{len(patterns) + 1}", key=pattern_key(trace), steps=trace.steps)
        patterns[pattern.key] = pattern
        return pattern


def pattern_key(trace: TraceRecord) -> str:
    skill = trace.skill.id if trace.skill else "none"
    return "|".join([trace.area, skill, ">".join(trace.steps), trace.outcome, trace.policy_check])


def steps_apart(a: list[str], b: list[str]) -> int:
    """Edit distance between two step sequences: how many steps to add, drop or swap to turn one into the other."""
    row = list(range(len(b) + 1))
    for i, step_a in enumerate(a, 1):
        previous, row[0] = row[0], i
        for j, step_b in enumerate(b, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (step_a != step_b))
    return row[-1]


def near_pattern(trace: TraceRecord, patterns: dict[str, Pattern]) -> Pattern | None:
    """Same skill, ending and policy check, and at most one step apart. Only this area's patterns are read."""
    head = pattern_key(trace).split("|")
    for pattern in patterns.values():
        other = pattern.key.split("|")
        if other[1] == head[1] and other[3:] == head[3:] and steps_apart(trace.steps, pattern.steps) <= NEAR_MATCH_STEPS:
            return pattern
    return None


def triage(trace: TraceRecord, store: PatternStore) -> AreaMatch:
    """Normal joins a pattern and counts; a surprise goes to a person. No Claude call, no scan beyond one area."""
    patterns = store.area(trace.tenant_id, trace.area)
    key = pattern_key(trace)
    exact = patterns.get(key)
    pattern = exact or near_pattern(trace, patterns)
    if pattern:
        pattern.count += 1
        pattern.examples = ([trace.trace_id] + pattern.examples)[:EXAMPLES_PER_PATTERN]
    return AreaMatch(trace_id=trace.trace_id, tenant_id=trace.tenant_id, area=trace.area, pattern_id=pattern.pattern_id if pattern else None,
                     pattern_key=key, similarity=1.0 if exact else NEAR_SIMILARITY if pattern else 0.0, match="normal" if pattern else "surprise")


# --- K18: the three drift checks

def security_drift(trace: TraceRecord, now: datetime) -> DriftFlag | None:
    """Zero tolerance: work that finished although an access check said deny. No draft: it goes to an L1 user."""
    denied = [a for a in trace.access if a.decision == "deny"]
    if trace.outcome != "resolved" or not denied:
        return None
    return DriftFlag(flag_id=f"dr-sec-{trace.trace_id}", tenant_id=trace.tenant_id, kind="security", area=trace.area,
                     subject=DriftSubject(type="agent", id=denied[0].principal_id, name=denied[0].principal_id),
                     summary="An action finished although its access check said deny", usual=0, latest=len(denied),
                     evidence_trace_ids=[trace.trace_id], state="detected", fix=None, recheck=None, reopened_note=None, raised_at=now)


def skill_drift(tenant_id: str, area: Area, skill: DriftSubject, follow_rates: list[float], evidence: list[str], fix: str, now: datetime) -> DriftFlag | None:
    """Weekly share of traces that follow the skill's steps; the latest week against the median of the weeks before."""
    if len(follow_rates) < 2:
        return None
    usual, latest = statistics.median(follow_rates[:-1]), follow_rates[-1]
    if usual - latest < SKILL_DRIFT_BAR:
        return None
    return DriftFlag(flag_id=f"dr-skill-{skill.id}", tenant_id=tenant_id, kind="skill", area=area, subject=skill,
                     summary="People follow the skill's steps less often", usual=usual, latest=latest, evidence_trace_ids=evidence,
                     state="sent_to_l1", fix=DriftFix(summary=fix, change_request_id=None), recheck=None, reopened_note=None, raised_at=now)


def policy_drift(tenant_id: str, area: Area, policy: DriftSubject, outside_counts: list[int], evidence: list[str], fix: str, now: datetime) -> DriftFlag | None:
    """Work outside the policy per week: the same spike bar as the Trends tab (3 times the usual week, at least 5)."""
    if len(outside_counts) < 2:
        return None
    usual, latest = statistics.median(outside_counts[:-1]), outside_counts[-1]
    if latest < SPIKE_MIN or latest < SPIKE_RATIO * usual:
        return None
    return DriftFlag(flag_id=f"dr-policy-{policy.id}", tenant_id=tenant_id, kind="policy", area=area, subject=policy,
                     summary="People work outside this policy more often", usual=usual, latest=latest, evidence_trace_ids=evidence,
                     state="sent_to_l1", fix=DriftFix(summary=fix, change_request_id=None), recheck=None, reopened_note=None, raised_at=now)


# --- K19: a steady pattern no skill covers becomes a draft

def skill_draft(pattern: Pattern, trace: TraceRecord, same_steps_total: int, latest_week_share: float) -> SkillDraft | None:
    """Enough support, and nearly every trace with these steps ends the same way. An L1 user decides; nothing goes live here."""
    same_outcome = pattern.count / max(1, same_steps_total)
    if trace.skill or pattern.count < DRAFT_MIN_SUPPORT or same_outcome < DRAFT_MIN_SAME_OUTCOME:
        return None
    return SkillDraft(draft_id=f"xs-{pattern.pattern_id}", tenant_id=trace.tenant_id, area=trace.area, pattern_id=pattern.pattern_id,
                      steps=pattern.steps, support=pattern.count, same_outcome_share=round(same_outcome, 2), follow_rate=latest_week_share,
                      state="draft", change_request_id=None)
