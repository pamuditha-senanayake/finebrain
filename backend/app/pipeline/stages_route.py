# stages_route.py: S3 Route. Matches a K2 signal to a resolver rule, pins the skill version, and builds K3.
# Rules, skills and agents come from the graph. Rules decide first; Claude settles close calls and, when no rule is
# clear, plans from the rules whose gates pass. Claude can only pick a listed rule, and its picks are flagged.
# Used by: orchestrate.py, tests. Uses: contracts_signal.py, observe.py, a graph (store_graph.py), a chooser (llm.py).
from datetime import datetime, timedelta

from app.pipeline.contracts_signal import Signal, TaskRequest, VersionRef
from app.pipeline.observe import count, log_event

# Config
MATCH_THRESHOLD = 0.72  # below this the signal goes to tasks.unrouted (reference doc section 8)
TIE_MARGIN = 0.1  # rules this close to the best are a tie for Claude to settle
SKIP_KINDS = {"document_arrived"}  # Lane B (S11) takes documents
PLANNED_FLAG = "planned_by_model"  # tells S7 a model, not a rule, chose this recipe


class GraphUnavailable(Exception):
    """The graph could not be read. A replay later may work."""
    retryable = True


class RouteConfigError(Exception):
    """A rule points at a skill or agent that does not exist. Someone must fix the rule."""
    retryable = False


# --- Reading and scoring

def read_routing(graph) -> dict:
    """Latest rules, skills and agents from the graph, in one place."""
    try:
        return {
            "rules": graph.latest("resolver_rule"),
            "skills": {node["_ref"]["id"]: node for node in graph.latest("skill")},
            "agents": {node["_ref"]["id"]: node for node in graph.latest("agent")},
        }
    except Exception as error:
        raise GraphUnavailable(type(error).__name__) from None


def rule_applies(rule: dict, signal: Signal) -> bool:
    """Kind, channel and required entities are gates: miss one and the rule does not apply."""
    entity_types = {entity.type for entity in signal.entities}
    return signal.kind in rule["kinds"] and signal.channel in rule["channels"] and set(rule["required_entities"]) <= entity_types


def score_rule(rule: dict, signal: Signal) -> float:
    """Share of the rule's keywords in the masked text, or 0 when a gate fails."""
    if not rule_applies(rule, signal):
        return 0.0
    text = (signal.text_masked or "").lower()
    return sum(1 for word in rule["keywords"] if word in text) / len(rule["keywords"])


# --- Choosing

def settle_tie(signal: Signal, contenders: list[dict], choose) -> dict | None:
    """Ask Claude to pick among close rules. A failure or an answer off the list means unresolved."""
    options = {rule["rule_id"]: rule["description"] for rule in contenders}
    try:
        picked = choose(signal.text_masked or "", options)
    except Exception as error:  # the tie-break is optional help, never a reason to crash the stage
        log_event("S3", "tie_break_failed", signal_id=signal.signal_id, error=type(error).__name__)
        return None
    return next((rule for rule in contenders if rule["rule_id"] == picked), None)


def pick_rule(signal: Signal, rules: list[dict], choose) -> tuple[dict | None, float, str]:
    """The winning rule, its score, and why: routed, planned, below_threshold or tie_unresolved."""
    scored = sorted(((score_rule(rule, signal), rule) for rule in rules), key=lambda pair: pair[0], reverse=True)
    best_score = scored[0][0] if scored else 0.0
    if best_score < MATCH_THRESHOLD:
        return plan_with_model(signal, rules, choose)
    contenders = [rule for score, rule in scored if score >= MATCH_THRESHOLD and best_score - score <= TIE_MARGIN]
    winner = contenders[0] if len(contenders) == 1 else settle_tie(signal, contenders, choose)
    return winner, best_score, "routed" if winner else "tie_unresolved"


def plan_with_model(signal: Signal, rules: list[dict], choose) -> tuple[dict | None, float, str]:
    """No rule is clear: Claude picks among rules whose gates pass, so it can never skip a required entity."""
    gated = [rule for rule in rules if rule_applies(rule, signal)]
    picked = settle_tie(signal, gated, choose) if gated else None
    if picked is None:
        best = max((score_rule(rule, signal) for rule in rules), default=0.0)
        return None, best, "below_threshold"
    return picked, score_rule(picked, signal), "planned"


def make_task(signal: Signal, rule: dict, score: float, routing: dict, new_id, now: datetime, flags: list[str]) -> TaskRequest:
    """Build K3, pinning the skill's released version so a release mid run cannot change it."""
    skill = routing["skills"].get(rule["skill_id"])
    if skill is None or rule["agent_id"] not in routing["agents"]:
        raise RouteConfigError(f"rule {rule['rule_id']} points at a missing skill or agent")
    return TaskRequest(
        task_id=new_id("task"), signal_ids=[signal.signal_id], activity_id=rule["activity_id"],
        skill_ref=VersionRef(**skill["_ref"]), agent_id=rule["agent_id"], on_behalf_of=None,
        resolver_rule_id=rule["rule_id"], match_score=round(score, 2), base_criticality=rule["base_criticality"],
        due_at=now + timedelta(hours=rule["due_hours"]), priority=rule["priority"], flags=flags,
    )


# --- S3 Route

def route(signal: Signal, routing: dict, choose, new_id, now: datetime) -> tuple[TaskRequest | None, str]:
    """S3: (task, "routed" or "planned"), or (None, reason) with reason lane_b, below_threshold or tie_unresolved."""
    # Seam in: the K2 that arrived, ids and labels only
    log_event("S3", "seam_in", signal_id=signal.signal_id, kind=signal.kind, channel=signal.channel, conversation_id=signal.conversation_id)
    if signal.kind in SKIP_KINDS:
        return None, "lane_b"

    # Step 1: rules first, then the model when no rule is clear
    live = [rule for rule in routing["rules"] if not rule.get("paused")]  # Studio pauses a rule with its workflow or skill
    rule, score, reason = pick_rule(signal, live, choose)
    count(f"s3.{reason}")
    log_event("S3", reason, signal_id=signal.signal_id, best_score=round(score, 2), rule_id=rule["rule_id"] if rule else None)
    if rule is None:
        return None, reason

    # Step 2: build K3 with the pinned skill; a model pick carries a flag so later stages can weigh it
    flags = signal.flags + ([PLANNED_FLAG] if reason == "planned" else [])
    task = make_task(signal, rule, score, routing, new_id, now, flags)
    log_event("S3", "seam_out", task_id=task.task_id, signal_ids=task.signal_ids, resolver_rule_id=task.resolver_rule_id,
              skill_ref=task.skill_ref.model_dump(), agent_id=task.agent_id, match_score=task.match_score, flags=task.flags)
    return task, reason
