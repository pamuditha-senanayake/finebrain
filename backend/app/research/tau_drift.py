# tau_drift.py: the tau Drift generator (spec section 6.2), on Finebrain's own refund domain first. The policy parameters
# that decide the action get dated versions whose text differs only in the value; each task is dated, its gold action is
# the one the version valid on that date gives, and tasks split into changed (the gold differs across versions) and
# unchanged; simulated handling yields an event log whose drift points are the dates the versions changed. Here the
# parameters are the two S7 enforces (the refund window and the automatic limit); tau's domains would add more.
# Used by: scripts/research_make_tau_drift_pack.py, tests. Uses: research/drift_eval.py (cases for the drift signal).
import json
import random
from datetime import date, timedelta

# Config
SEED = 20261028
POLICY = "policy_refund"
WINDOW = [(date(2026, 1, 1), 30), (date(2026, 5, 1), 45), (date(2026, 9, 1), 21)]  # (valid from, refund window in days)
LIMIT = [(date(2026, 1, 1), 5_000_000), (date(2026, 7, 1), 7_500_000)]  # (valid from, automatic limit in minor units)
TEXT = "Refunds are accepted within {days} days of purchase. Refunds up to LKR {limit:,} are approved automatically; larger ones need a person."
START, END, CASES = date(2026, 1, 15), date(2026, 12, 15), 6_000  # about 16 requests a day: versions change about 1,100 cases apart


def value_on(versions: list[tuple[date, int]], on: date) -> int:
    return [v for start, v in versions if start <= on][-1]


def gold(on: date, age_days: int, amount_minor: int) -> str:
    """The route the policy valid on that day gives: refund now, or wait for a person."""
    return "execute" if age_days <= value_on(WINDOW, on) and amount_minor <= value_on(LIMIT, on) else "approval_required"


def changes() -> list[date]:
    return sorted({start for start, _ in WINDOW[1:]} | {start for start, _ in LIMIT[1:]})


def policies() -> list[dict]:
    """One version per day either parameter changes, each stating both values, worded identically but for them."""
    days = [START.replace(month=1, day=1), *changes()]
    ends = [d.isoformat() for d in days[1:]] + [None]
    return [{"policy_id": POLICY, "version": n + 1, "valid_from": d.isoformat(), "valid_to": ends[n],
             "statement": TEXT.format(days=value_on(WINDOW, d), limit=value_on(LIMIT, d) // 100),
             "params": {"window_days": value_on(WINDOW, d), "auto_limit_minor": value_on(LIMIT, d)}} for n, d in enumerate(days)]


def tasks(rng: random.Random) -> list[dict]:
    """Dated refund requests, in date order. changed: some version would route it differently."""
    found = []
    for n in range(CASES):
        on = START + timedelta(days=(END - START).days * n // CASES)
        age, amount = rng.randrange(1, 60), rng.randrange(500_000, 9_000_000, 50_000)
        routes = {gold(start, age, amount) for start in [START, *changes()]}
        found.append({"task_id": f"TD-{n:04d}", "as_of": on.isoformat(), "policy_ids": [POLICY],
                      "user_message": f"Please refund my order: bought {age} days ago for LKR {amount // 100:,}.",
                      "initial_state": {"age_days": age, "amount_minor": amount, "changed": len(routes) > 1},
                      "expected_actions": [{"name": "issue_refund", "route": gold(on, age, amount), "amount_minor": amount}]})
    return found


def activities_of(task: dict) -> list[str]:
    route = task["expected_actions"][0]["route"]
    return ["retrieve_context", "propose_issue_refund", "access_allow", *(["await_approval"] if route == "approval_required" else []), "act_issue_refund"]


def drift_points(found: list[dict]) -> list[dict]:
    """Each version change as a sudden drift at the first case dated on or after it."""
    return [{"policy_id": POLICY, "change_at_case_index": next(i for i, t in enumerate(found) if t["as_of"] >= d.isoformat()), "change_at_time": d.isoformat(), "type": "sudden"}
            for d in changes()]


def cases(found: list[dict]) -> list[dict]:
    """The tasks as the drift signal reads cases."""
    return [{"activities": activities_of(t), "durations": {}} for t in found]


def build() -> dict[str, str]:
    """The pack's files (policy_drift kind), without manifest."""
    found = tasks(random.Random(SEED))
    xes = ['<?xml version="1.0" encoding="UTF-8"?>', '<log xes.version="1.0" xmlns="http://www.xes-standard.org/">', '<string key="concept:name" value="tau_drift_refund"/>']
    for t in found:
        xes.append(f'<trace><string key="concept:name" value="{t["task_id"]}"/>')
        xes += [f'<event><string key="concept:name" value="{a}"/><date key="time:timestamp" value="{t["as_of"]}T{9 + i:02d}:00:00+05:30"/></event>' for i, a in enumerate(activities_of(t))]
        xes.append("</trace>")
    rows = lambda items: "".join(json.dumps(i) + "\n" for i in items)
    return {"tasks.jsonl": rows(found), "gold.jsonl": rows({"task_id": t["task_id"], "expected": {"actions": t["expected_actions"]}} for t in found),
            "policies.jsonl": rows(policies()), "drift_points.jsonl": rows(drift_points(found)), "event_log.xes": "\n".join(xes + ["</log>"]) + "\n",
            "alphabet.json": json.dumps(sorted({a for t in found for a in activities_of(t)})),
            "README.md": f"tau Drift on the Finebase refund domain (seed {SEED}): {CASES} dated refund requests; versions change on {', '.join(d.isoformat() for d in changes())}.\n"}
