# studio_spec.py: the parts of the console's Studio field table (frontend/lib/studio/spec.ts) the server review needs:
# each field's label and type, which fields point at other items, and which touch personal data. Keep the two in step.
# Used by: studio_findings.py, studio_review.py. Uses: nothing local.
import re

# Config: (key, label, type, points at, how the link reads, sensitive)
FIELDS: dict[str, list[tuple[str, str, str, str | None, str | None, str | None]]] = {
    "skill": [("trigger", "Trigger", "text", None, None, None), ("steps", "Steps", "list", None, None, None), ("agents", "Run by agents", "refs", "agent", "run by", None),
              ("tools", "Tools", "refs", "tool", "uses", None), ("policies", "Governing policies", "refs", "policy", "governed by", None),
              ("templates", "Fills templates", "refs", "template", "fills", None), ("inputs", "Reads sensors", "refs", "sensor", "reads", None),
              ("outputs", "Outputs", "list", None, None, None), ("evalCases", "Eval cases", "number", None, None, None)],
    "agent": [("autonomy", "Autonomy", "select", None, None, None), ("capabilities", "Capabilities", "list", None, None, None), ("accessLevel", "Access level", "select", None, None, None),
              ("model", "Model", "text", None, None, None), ("maxConcurrent", "Max concurrent tasks", "number", None, None, None)],
    "policy": [("statement", "Statement", "longtext", None, None, None), ("ruleKind", "Rule kind", "text", None, None, None), ("criticality", "Criticality", "select", None, None, None),
               ("validFrom", "Valid from", "text", None, None, None)],
    "template": [("cadence", "Cadence", "text", None, None, None), ("fieldList", "Fields", "list", None, None, None), ("freshnessRule", "Freshness rule", "text", None, None, None),
                 ("requiredEvidence", "Required evidence", "list", None, None, None), ("sensors", "Fed by sensors", "refs", "sensor", "fed by", None)],
    "sensor": [("source", "Source", "text", None, None, None), ("sensorKind", "Sensor kind", "select", None, None, None), ("events", "Events", "list", None, None, None),
               ("feeds", "Feeds agents", "refs", "agent", "feeds", None), ("retentionDays", "Retention", "number", None, None, "personal"),
               ("personalData", "Carries personal data", "boolean", None, None, "personal"), ("health", "Health", "select", None, None, None)],
    "scheduler": [("cron", "Cron", "text", None, None, None), ("timezone", "Timezone", "text", None, None, None), ("target", "Runs skill", "ref", "skill", "triggers", None),
                  ("agent", "On agent", "ref", "agent", "wakes", None), ("enabled", "Enabled", "boolean", None, None, None), ("catchUp", "Run missed slots", "boolean", None, None, None)],
    "loop": [("signal", "Signal sensors", "refs", "sensor", "senses", None), ("guards", "Guard policies", "refs", "policy", "guarded by", None),
             ("actions", "Action tools", "refs", "tool", "acts with", None), ("gate", "Quality gate", "text", None, None, None),
             ("learning", "Learns into template", "ref", "template", "learns into", None), ("reviewCadence", "Review cadence", "text", None, None, None)],
    "tool": [("level", "Kind of tool", "select", None, None, None), ("endpoint", "Endpoint", "text", None, None, None), ("capability", "Required capability", "text", None, None, None),
             ("sensitivity", "Sensitivity", "select", None, None, None), ("sideEffect", "Side effect", "select", None, None, None),
             ("rateLimitPerMin", "Rate limit", "number", None, None, None), ("code", "Code", "longtext", None, None, None)],
}
COMMON_LABELS = {"name": "Name", "description": "Description", "topics": "Topics", "status": "Status", "dri": "DRI"}
PARAM_LABELS = {"days": "Window in days", "amountMinor": "Amount limit", "currency": "Currency"}
KIND_LABEL = {"workflow": "Workflow", "skill": "Skill", "agent": "Agent", "policy": "Policy", "template": "Template", "sensor": "Sensor",
              "scheduler": "Scheduler", "loop": "Loop", "tool": "Tool"}
TOOL_LEVEL_LABEL = {"prebuilt": "Ready-made", "configured": "Set up", "custom": "Custom code"}
CRON = re.compile(r"^(\*|[0-9,\-/*]+)\s+(\*|[0-9,\-/*]+)\s+(\*|[0-9,\-/*]+)\s+(\*|[0-9,\-/*]+)\s+(\*|[0-9,\-/*A-Za-z]+)$")


def spec(kind: str, key: str):
    return next((row for row in FIELDS.get(kind, []) if row[0] == key), None)


def is_ref(kind: str, key: str) -> bool:
    row = spec(kind, key)
    return bool(row and row[2] in ("refs", "ref"))


def label(kind: str, key: str) -> str:
    if key.startswith("param."):
        return PARAM_LABELS.get(key.removeprefix("param."), key.removeprefix("param."))
    row = spec(kind, key)
    return COMMON_LABELS.get(key) or (row[1] if row else re.sub(r"([A-Z])", r" \1", key).capitalize())


def refs_of(kind: str, fields: dict) -> list[dict]:
    """Every link from an item to another, read from its ref fields."""
    found = []
    for key, _, kind_of_field, points_at, rel, _ in FIELDS.get(kind, []):
        if kind_of_field not in ("refs", "ref"):
            continue
        value = fields.get(key)
        for ref_id in value if isinstance(value, list) else [value] if isinstance(value, str) and value else []:
            found.append({"key": key, "ref": points_at, "rel": rel or "uses", "id": ref_id})
    return found


def format_value(value, key: str = "") -> str | None:
    if value is None or value == "" or value == []:
        return None
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and key.endswith("Minor"):
        return f"{value / 100:,.0f}" if value % 100 == 0 else f"{value / 100:,.2f}"
    if isinstance(value, (int, float)) and key.lower().endswith("days"):
        return f"{value} days"
    return str(value)


def valid_cron(text: str) -> bool:
    return bool(CRON.match(text.strip()))
