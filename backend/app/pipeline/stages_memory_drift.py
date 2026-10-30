# stages_memory_drift.py: drift on real data (stage 6). Security drift is raised the moment a trace shows a finished action
# whose access said deny. Skill and policy drift are read each night from the pattern counts, never by listing traces: a
# skill's usual path losing its share, or work outside a policy spiking. Steady patterns no skill covers become skill drafts
# (K19). Every flag goes out as K18 and waits in To review; api/memory_fixes.py drafts the fix and asks an L1 user. Approved
# fixes are re-checked for 14 days: the drift dropped (resolved) or it did not (reopened, with a note).
# Used by: stages_memory_flow.py (security), api/distiller.py (the night), api/memory_fixes.py, tests/test_memory_drift.py.
# Uses: stages_memory.py, stages_learn.py (weeks), store_drift.py, store_patterns.py, observe.py.
import re
from datetime import datetime, timedelta
from typing import get_args

from app.pipeline import stages_memory as memory
from app.pipeline.contracts_memory import Area, DriftFlag, DriftRecheck, DriftSubject, TraceRecord
from app.pipeline.observe import count, log_event
from app.pipeline.stages_learn import week_of, zone_of

# Config: Docs/CB_Living_Memory_Architecture.md sections 7, 8, 8b and 13
REVIEW_KIND = "memory_drift_review"  # records kind keyed by flag id: a drift waiting in To review
DRAFT_KIND = "memory_skill_draft"  # records kind keyed by draft id: a skill drafted from a steady pattern (K19)
WEEKS = 12
MIN_WEEKS = 3  # a skill or policy needs this many weeks with work before its drift is judged
RECHECK_DAYS = 14
AGAIN = "drifted again"
AREAS = sorted(get_args(Area))
DAYS = re.compile(r"(\d+) days since purchase")


# --- Raising

def raise_drift(lane, flag: DriftFlag, cause=None) -> DriftFlag:
    """Keep the flag (or add its evidence to the open one), tell To review once, and publish K18 when it is new."""
    kept, new = lane.drift.raise_flag(flag)
    if new:
        lane.records.save(REVIEW_KIND, kept.flag_id, kept)
        lane.bus.publish("drift.flags", "drift.raised", kept, "memory", cause)
        count(f"memory.drift_raised.{kept.kind}")
    elif kept.state == "approved":  # during the re-check the same drift came back: the night will reopen it
        lane.drift.move(kept, lane.now, AGAIN)
    return kept


def check_security(lane, trace: TraceRecord, cause=None) -> DriftFlag | None:
    """Zero tolerance, at once: a finished action whose access check said deny. No draft: it goes to an L1 user."""
    flag = memory.security_drift(trace, lane.now)
    return raise_drift(lane, flag, cause) if flag else None


# --- Weekly series from the pattern counts

def week_series(lane, pattern_ids: list[str]) -> list[dict]:
    """The last WEEKS weeks, oldest first, each the count per pattern. Read by pattern id, one small query each."""
    weeks = [week_of(lane.now, zone_of(lane)) - timedelta(weeks=n) for n in range(WEEKS - 1, -1, -1)]
    counts = {pid: lane.patterns.weeks(pid) for pid in pattern_ids}
    return [{pid: counts[pid].get(week, 0) for pid in pattern_ids} for week in weeks]


def by_skill(patterns: list[memory.Pattern]) -> dict[str, list[memory.Pattern]]:
    grouped: dict[str, list[memory.Pattern]] = {}
    for pattern in patterns:
        skill = pattern.key.split("|")[1]
        if skill != "none":
            grouped.setdefault(skill, []).append(pattern)
    return grouped


def skill_rates(lane, patterns: list[memory.Pattern]) -> tuple[list[float], memory.Pattern, memory.Pattern]:
    """The weekly share of the skill's work on its usual path, the usual path, and the path the latest week took most."""
    series = week_series(lane, [p.pattern_id for p in patterns])
    before = {p.pattern_id: sum(week[p.pattern_id] for week in series[:-1]) for p in patterns}
    usual = max(patterns, key=lambda p: (before[p.pattern_id], p.key))
    latest = max(patterns, key=lambda p: (series[-1][p.pattern_id], p.key))
    rates = [week[usual.pattern_id] / sum(week.values()) for week in series if sum(week.values())]
    return rates, usual, latest


def check_skills(lane, area: str) -> list[DriftFlag]:
    raised = []
    for skill, patterns in by_skill(list(lane.patterns.area_patterns(area).values())).items():
        rates, usual, latest = skill_rates(lane, patterns)
        if len(rates) < MIN_WEEKS or usual is latest:
            continue
        fix = f"Make the usual path what people now do: {' → '.join(latest.steps)}"
        flag = memory.skill_drift(lane.seed["tenant_id"], area, DriftSubject(type="skill", id=skill, name=skill), rates, latest.examples, fix, lane.now)
        if flag:
            raised.append(raise_drift(lane, flag))
    return raised


# --- Policy drift

def policy_of(lane, pattern: memory.Pattern) -> DriftSubject | None:
    """The policy the pattern's work was held to, read from one of its traces."""
    trace = next((t for trace_id in pattern.examples if (t := lane.traces.get(trace_id))), None)
    if not trace or not trace.policies:
        return None
    ref = trace.policies[0].policy_ref
    return DriftSubject(type="policy", id=ref.id, name=ref.id)


def window_fix(lane, patterns: list[memory.Pattern]) -> str:
    """A new refund window that would cover the late work people now do, rounded up to five days."""
    days = [int(m.group(1)) for p in patterns for trace_id in p.examples if (t := lane.traces.get(trace_id)) for line in t.why if (m := DAYS.search(line))]
    if not days:
        return "Review this policy: people now often work outside it"
    longest = sorted(days)[int(len(days) * 0.9) - 1 if len(days) > 1 else 0]
    return f"Refund window: up to {-(-longest // 5) * 5} days, as people now refund"


def check_policies(lane, area: str) -> list[DriftFlag]:
    outside = [p for p in lane.patterns.area_patterns(area).values() if p.key.endswith("|outside")]
    by_policy: dict[str, tuple[DriftSubject, list[memory.Pattern]]] = {}
    for pattern in outside:
        subject = policy_of(lane, pattern)
        if subject:
            by_policy.setdefault(subject.id, (subject, []))[1].append(pattern)
    raised = []
    for subject, patterns in by_policy.values():
        weekly = [sum(week.values()) for week in week_series(lane, [p.pattern_id for p in patterns])]
        evidence = [trace_id for p in patterns for trace_id in p.examples]
        flag = memory.policy_drift(lane.seed["tenant_id"], area, subject, weekly, evidence, window_fix(lane, patterns), lane.now)
        if flag and sum(1 for w in weekly if w) >= MIN_WEEKS:
            raised.append(raise_drift(lane, flag))
    return raised


# --- Skill drafts from steady patterns (K19)

def draft_skills(lane, area: str) -> int:
    """A pattern no skill covers, with enough support and one ending, becomes a draft once."""
    patterns = list(lane.patterns.area_patterns(area).values())
    drafted = 0
    for pattern in (p for p in patterns if p.key.split("|")[1] == "none"):
        same_steps = sum(p.count for p in patterns if p.steps == pattern.steps)
        latest = week_series(lane, [pattern.pattern_id])[-1][pattern.pattern_id]
        trace = next((t for trace_id in pattern.examples if (t := lane.traces.get(trace_id))), None)
        draft = memory.skill_draft(pattern, trace, same_steps, round(latest / max(1, pattern.count), 2)) if trace else None
        if draft and not lane.records.load(DRAFT_KIND, draft.draft_id):
            draft = draft.model_copy(update={"created_at": lane.now})
            lane.records.save(DRAFT_KIND, draft.draft_id, draft)
            lane.bus.publish("skills.drafted", "skill.drafted", draft, "memory")
            drafted += 1
    return drafted


# --- The 14-day re-check

def still_drifting(lane, flag: DriftFlag) -> bool:
    """Did the same drift come back after the fix went live? Its history says so (raise_drift notes it)."""
    approved = max((e["at"] for e in lane.drift.history(flag.flag_id) if e["state"] == "approved"), default="")
    return any(e["note"] == AGAIN and e["at"] >= approved for e in lane.drift.history(flag.flag_id))


def recheck(lane) -> dict[str, int]:
    """Each approved fix: drifting again means reopen; 14 quiet days means resolved; otherwise keep watching."""
    done = {"resolved": 0, "reopened": 0}
    for flag in lane.drift.in_state("approved"):
        until = flag.recheck.until if flag.recheck else lane.now
        if still_drifting(lane, flag):
            note = "The approved fix did not hold: the drift came back during the 14-day re-check"
            lane.drift.move(flag.model_copy(update={"state": "detected", "reopened_note": note, "recheck": DriftRecheck(until=until, result="still_drifting")}), lane.now, "reopened")
            done["reopened"] += 1
        elif lane.now >= until:
            lane.drift.move(flag.model_copy(update={"state": "resolved", "recheck": DriftRecheck(until=until, result="dropped")}), lane.now, "resolved")
            done["resolved"] += 1
    return done


def approved_until(lane) -> datetime:
    return lane.now + timedelta(days=RECHECK_DAYS)


# --- The night

def night(lane) -> dict:
    """The drift part of the living memory's night: checks area by area, drafts, then the re-checks."""
    skills = sum(len(check_skills(lane, area)) for area in AREAS)
    policies = sum(len(check_policies(lane, area)) for area in AREAS)
    drafts = sum(draft_skills(lane, area) for area in AREAS)
    rechecked = recheck(lane)
    log_event("memory", "drift_night", skills=skills, policies=policies, drafts=drafts, **rechecked)
    return {"skill_drift": skills, "policy_drift": policies, "skill_drafts": drafts, **rechecked}
