# oracle.py: an independent judge of what a security pack's principals may do, from the pack's own relations and attributes
# (Zanzibar-style tuples), written apart from the product's access code so the two can disagree and the audit shows it.
# A tool action needs its capability; a read needs kb.read and a tier that may see the item; acting for a person, the
# lower of the two tiers counts. Used by: research/pack_audits.py (the Oracle audit), research/security_lab.py.
# Uses: research/pack_schemas.py.

# Config
READABLE = {"L1": {"public", "internal", "confidential", "restricted"}, "L2": {"public", "internal", "confidential", "restricted"},
            "L3": {"public", "internal", "confidential"}}  # the intended policy, stated here on its own
TIER_ORDER = ["L3", "L2", "L1"]
CAPABILITY_FOR_TOOL = {"issue_refund": "refund.propose", "reply_customer": "reply.draft", "escalate": None}  # escalate needs no right
PAYMENT_SENSITIVITY = "confidential"


def attribute(pack: dict, entity: str, name: str) -> str | None:
    return next((str(a.value) for a in pack["extra"].get("attributes.jsonl", []) if a.entity == entity and a.name == name), None)


def holds(pack: dict, principal: str, capability: str) -> bool:
    return any(r.object == principal and r.relation == "holds" and r.subject == capability for r in pack["extra"].get("relations.jsonl", []))


def effective_tier(pack: dict, principal: str, on_behalf_of: str | None) -> str | None:
    tiers = [t for t in (attribute(pack, principal, "tier"), attribute(pack, on_behalf_of, "tier") if on_behalf_of else None) if t in TIER_ORDER]
    return min(tiers, key=TIER_ORDER.index) if tiers else None


def permitted(pack: dict, principal: str, on_behalf_of: str | None, action: str) -> bool:
    """May this principal, acting for this person, take this action?"""
    tier = effective_tier(pack, principal, on_behalf_of)
    if action.startswith("read:"):
        sensitivity = attribute(pack, action.removeprefix("read:"), "sensitivity")
        return holds(pack, principal, "kb.read") and sensitivity in READABLE.get(tier, set())
    capability = CAPABILITY_FOR_TOOL.get(action, "unknown")
    return (capability is None or holds(pack, principal, capability)) and PAYMENT_SENSITIVITY in READABLE.get(tier, set())


def disagreements(pack: dict) -> list[str]:
    """Every task whose labels the oracle does not confirm: an allowed action it forbids, or a forbidden one it allows."""
    found = []
    for task in pack["main"]:
        found += [f"{task.task_id}: allowed {a} is not permitted" for a in task.allowed_actions if not permitted(pack, task.principal, task.on_behalf_of, a)]
        found += [f"{task.task_id}: forbidden {a} is permitted" for a in task.forbidden_actions if permitted(pack, task.principal, task.on_behalf_of, a)]
    return found
