# stages_route.py: S3 Route, matching a K2 signal to an activity, pinned skill version and agent (K3).
# Used by: tests/test_stages.py. Uses: contracts_signal.py.
# Step 2 is keyword scoring only. The Haiku tie-break comes when stages get thicker (step 7).
from datetime import datetime, timedelta

from app.pipeline.contracts_signal import Signal, TaskRequest, VersionRef

# Config
MATCH_THRESHOLD = 0.72  # below this the signal goes to tasks.unrouted (reference doc section 8)


def score_rule(rule: dict, signal: Signal) -> float:
    """Share of the rule's keywords found in the masked text."""
    text = (signal.text_masked or "").lower()
    hits = sum(1 for word in rule["keywords"] if word in text)
    return hits / len(rule["keywords"])


def route(signal: Signal, rules: list[dict], new_id, now: datetime) -> TaskRequest | None:
    """S3: pick the best rule, or None so the caller sends the signal to tasks.unrouted."""
    # Step 1: score every rule and keep the best
    best = max(rules, key=lambda rule: score_rule(rule, signal), default=None)
    score = score_rule(best, signal) if best else 0.0
    if score < MATCH_THRESHOLD:
        return None

    # Step 2: pin the skill version now, so a release mid run cannot change it
    return TaskRequest(
        task_id=new_id("task"), signal_ids=[signal.signal_id], activity_id=best["activity_id"],
        skill_ref=VersionRef(**best["skill_ref"]), agent_id=best["agent_id"], on_behalf_of=None,
        resolver_rule_id=best["rule_id"], match_score=round(score, 2),
        base_criticality=best["base_criticality"],
        due_at=now + timedelta(hours=best["due_hours"]), priority=best["priority"],
    )
