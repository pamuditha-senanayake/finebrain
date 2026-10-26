# studio_rules.py: how risky a Studio change is and who may confirm it. Base level by kind and intent, one step up when
# it touches money, personal data, public content or another cluster, at least C2 when breaking; then the route: apply
# now, send for approval, or view only. An L1 is the top of the chain, so their own change applies at once up to their
# ceiling (C4) and is logged; L2 sends for approval. A port of baseLevel, touchesFor and authorityFor in the mock engine.
# Used by: studio_review.py. Uses: studio_spec.py, studio_state.py, views.py (MAX_APPROVAL).
from app.api.studio_spec import refs_of, spec
from app.api.views import MAX_APPROVAL

# Config
WORDING = {"name", "description", "topics"}
APPROVER = {0: ("L2", 0, "Automatic and logged"), 1: ("L2", 0, "L2 supervisor agent, steward notified"), 2: ("L2", 1, "L2 human steward"),
            3: ("L1", 1, "L1 DRI"), 4: ("L1", 2, "Two L1 approvers")}


def base_level(change: dict, fields: list[str], before: dict | None, after: dict | None) -> tuple[int, str]:
    intent, kind = change["intent"], change["kind"]
    if intent == "update" and fields and all(f == "topics" for f in fields):
        return 0, "a topic change starts at C0"
    if intent == "update" and all(f in WORDING for f in fields):
        return 1, "a wording change starts at C1"
    if kind == "workflow":
        if intent == "update" and "status" not in fields:
            return 1, "a workflow setting change starts at C1"
        return (2, "a new workflow starts at C2") if intent == "create" else (3, "pausing, retiring or deleting a workflow starts at C3")
    after_fields, before_fields = (after or {}).get("fields", {}), (before or {}).get("fields", {})
    if kind == "tool":
        if after_fields.get("level") == "custom" and intent != "delete" and (intent == "create" or {"code", "level"} & set(fields)):
            return 3, "custom tool code starts at C3, so a person approves it once before agents call it"
        return (2, "a new shared tool starts at C2") if intent == "create" else (3, "a shared tool change starts at C3, since other workflows depend on it")
    word = {"update": "change", "create": "addition", "delete": "removal"}[intent]
    if kind == "policy":
        return 3, f"a policy {word} starts at C3"
    if kind == "skill":
        return (2, "a skill edit starts at C2") if intent == "update" else (3, f"a skill {word} starts at C3")
    if kind == "agent":
        added = [c for c in after_fields.get("capabilities", []) if c not in before_fields.get("capabilities", [])]
        if added:
            return 4, f"granting {', '.join(added)} is a capability grant, C4"
        if after_fields.get("autonomy") == "autonomous" and before_fields.get("autonomy") != "autonomous":
            return 3, "making an agent autonomous starts at C3"
        return 2, f"an agent {word} starts at C2"
    if kind == "sensor":
        return 2, "a data scope change starts at C2"
    if kind == "loop":
        return 2, "a loop change starts at C2"
    if kind == "scheduler":
        return (2, "stopping or removing a schedule starts at C2") if "enabled" in fields or intent == "delete" else (1, "a timing change starts at C1")
    return 1, "a template change starts at C1"


def touches(st, kind: str, target: dict | None, fields: list[str]) -> dict:
    """What the change reaches: money, public content, personal data."""
    found = {"money": False, "public": False, "personal": False}
    if not target or kind == "workflow":
        return found
    tools = [target] if kind == "tool" else [st.items[r["id"]] for r in refs_of(kind, target["fields"]) if r["ref"] == "tool" and r["id"] in st.items]
    found["money"] = any(t["fields"].get("sideEffect") == "money" for t in tools) or (kind == "policy" and any("amount" in f.lower() or "minor" in f.lower() for f in fields))
    found["public"] = any(t["fields"].get("sideEffect") == "public" for t in tools)
    found["personal"] = (kind == "sensor" and (target["fields"].get("personalData") is True or bool({"retentionDays", "personalData"} & set(fields)))) \
        or any((spec(kind, f) or (None,) * 6)[5] == "personal" for f in fields)
    return found


def level_for(change: dict, fields: list[str], before, after, verdict: str, reach: dict, clusters: int) -> tuple[int, list[str]]:
    level, reason = base_level(change, fields, before, after)
    reasons = [reason]
    bumps = [why for why, hit in (("touches money", reach["money"] and level < 3), ("touches personal data", reach["personal"]),
                                  ("touches public content", reach["public"] and level < 3), ("spans more than one cluster", clusters > 1)) if hit]
    if bumps and level < 4:
        level += 1
        reasons.append(f"moves up one level because it {', '.join(bumps)}")
    if verdict == "breaking" and level < 2:
        level = 2
        reasons.append("breaking changes always need a human approver, so at least C2")
    return level, reasons


def authority(person_id: str, person: dict, flow: dict | None, level: int, verdict: str) -> dict:
    """Apply now, send for approval, or view only, and why."""
    tier, ceiling = person["tier"], MAX_APPROVAL[person["tier"]]
    if tier == "L3":
        return {"canApply": False, "route": "view_only", "approver": "the workflow DRI" if flow else "an L2 steward", "reason": "L3 can view workflows and suggest edits, but cannot change them."}
    if tier == "L2":
        return {"canApply": False, "route": "approval", "approver": APPROVER[max(level, 2)][2], "reason": "L2 drafts changes and sends them for approval. It cannot apply a change itself."}
    if level > ceiling:
        return {"canApply": False, "route": "approval", "approver": APPROVER[level][2], "reason": f"C{level} is above your ceiling of C{ceiling}."}
    if level <= 1 and verdict != "breaking":
        return {"canApply": True, "route": "apply", "approver": "you", "reason": f"C{level} is logged and applied right away."}
    warning = " The Edit Review Agent marked it breaking, so check the diagram first." if verdict == "breaking" else ""
    return {"canApply": True, "route": "apply", "approver": "you", "reason": f"You are L1, so C{level} applies on your own approval and is logged.{warning}"}
