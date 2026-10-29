# intake_policy.py: what every document must say about itself before it joins the knowledge base, and how the intake
# agent (Lisena) asks for what is missing. One source of truth: the schema, the policy, the skill steps and the questions
# all live here, and the console shows them as they are. Used by: intake.py, tests/test_intake.py.
import re
from datetime import date, timedelta

# Config
KINDS = {
    "meeting": "Meeting record",
    "contract": "Contract",
    "proposal": "Proposal",
    "policy": "Company policy",
    "report": "Report",
    "spec": "Spec or plan",
    "other": "Other document",
}
ABOUT = {"company": "The company", "client": "A client", "project": "A project"}
MEETING_TYPES = {"client": "Client meeting", "internal": "Internal meeting", "project": "Project meeting"}
# Each field: the question Lisena asks, how it is answered, and which kinds need it ("*" is every kind).
FIELDS = {
    "kind": {"ask": "What kind of document is this?", "type": "choice", "options": KINDS, "for": "*"},
    "title": {"ask": "What should we call it?", "type": "text", "for": "*"},
    "date": {"ask": "What date is it from?", "type": "date", "for": "*"},
    "about": {"ask": "Is it about the company, a client or a project?", "type": "choice", "options": ABOUT, "for": "*"},
    "about_name": {"ask": "Which client or project?", "type": "text", "for": "client_or_project"},
    "owner": {"ask": "Who owns it on our side?", "type": "text", "for": "*"},
    "meeting_type": {"ask": "What kind of meeting was it?", "type": "choice", "options": MEETING_TYPES, "for": "meeting"},
    "attendees": {"ask": "Who attended? Separate names with commas.", "type": "list", "for": "meeting"},
    "topic": {"ask": "What was the meeting about, in a few words?", "type": "text", "for": "meeting"},
    "parties": {"ask": "Who are the parties to it? Separate names with commas.", "type": "list", "for": "contract"},
}
POLICY = [
    "Nothing joins the knowledge base until every required field is filled.",
    "Every document says what it is, its date, who owns it, and whether it is about the company, a client or a project.",
    "A meeting also says its type, who attended and its topic.",
    "Meeting records are what was said, never company rules. Only a person can promote an agreed point to the Vault.",
    "The original file is kept untouched in raw storage. What is filed can be switched off at any time.",
]
SKILL_STEPS = [
    "Read the file and say what kind of document it looks like.",
    "Fill every field the text answers: kind, title, date, owner, client or project, and for a meeting its type, attendees and topic.",
    "Ask one short question for each required field still empty. Offer choices when there are some.",
    "Show everything on one card and wait for the person to confirm.",
    "Keep the original in raw storage, file the text in memory under its client or project, and list it in the Library.",
    "For a meeting, mark each line Agreed, Suggested, Action or Discussed, so answers can say what was agreed.",
]
DEFAULT_RULES = {  # which fields each kind needs; Studio's "Document details" policy can change these (brain_workflows.py)
    "*": ["kind", "title", "date", "about", "owner"], "meeting": ["meeting_type", "attendees", "topic"], "contract": ["parties"], "client_or_project": ["about_name"]}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
SPOKEN_DATE = re.compile(r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3})[a-z]*|([a-z]{3})[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?)(?:,?\s+(\d{4}))?", re.I)
LINE_TAGS = [  # first match wins; a meeting line with none of these is Discussed
    ("Agreed", re.compile(r"\b(agreed|we agree|decided|decision|confirmed|signed off|approved)\b", re.I)),
    ("Action", re.compile(r"\b(action item|to ?do|will send|will share|will follow up|by (monday|tuesday|wednesday|thursday|friday|next week|tomorrow)|owner:)\b", re.I)),
    ("Suggested", re.compile(r"\b(suggest\w*|propos\w*|maybe|could we|what if|idea|recommend\w*)\b", re.I)),
]


def required(fields: dict, rules: dict | None = None) -> list[str]:
    """The fields this document must have, in the order Lisena asks for them."""
    rules = rules or DEFAULT_RULES
    wanted = set(rules.get("*", []) + rules.get(fields.get("kind") or "", []))
    if fields.get("about") in ("client", "project"):
        wanted |= set(rules.get("client_or_project", []))
    return [name for name in FIELDS if name in wanted]


def choice(spec: dict, text: str) -> str | None:
    """A choice by its id or its words: "client", "A client", "it's a client meeting" all answer client."""
    said = text.lower()
    if said in spec["options"]:
        return said
    for option_id, label in spec["options"].items():
        if said in (label.lower(), label.lower().removeprefix("a ").removeprefix("the ")):
            return option_id
    hits = [option_id for option_id, label in spec["options"].items() if re.search(rf"\b{re.escape(option_id)}\b", said) or label.lower() in said]
    return hits[0] if len(hits) == 1 else None


def spoken_date(text: str, today: date | None = None) -> str | None:
    """2026-10-12, "12 October", "October 12, 2026", "today" or "yesterday"; None for anything else."""
    today = today or date.today()
    said = text.strip().lower()
    try:
        return date.fromisoformat(said[:10]).isoformat()
    except ValueError:
        pass
    if "yesterday" in said:
        return (today - timedelta(days=1)).isoformat()
    if "today" in said:
        return today.isoformat()
    found = SPOKEN_DATE.search(said)
    if not found:
        return None
    day, month = (found.group(1), found.group(2)) if found.group(1) else (found.group(4), found.group(3))
    if month[:3] not in MONTHS:
        return None
    try:
        return date(int(found.group(5) or today.year), MONTHS[month[:3]], int(day)).isoformat()
    except ValueError:
        return None


def clean(name: str, value) -> object | None:
    """The value as stored, or None when it does not answer the field (an unknown choice, a bad date, an empty list)."""
    spec = FIELDS.get(name)
    if spec is None or value is None:
        return None
    if spec["type"] == "list":
        items = value if isinstance(value, list) else re.split(r",|\band\b|&", str(value))
        names = [str(item).strip(" .") for item in items if str(item).strip(" .")]
        return names or None
    text = str(value).strip()
    if spec["type"] == "choice":
        return choice(spec, text)
    if spec["type"] == "date":
        return spoken_date(text)
    return text[:200] or None


def missing(fields: dict, rules: dict | None = None) -> list[dict]:
    """One question per required field still empty: what Lisena asks next, first one first."""
    return [{"field": name, "question": FIELDS[name]["ask"], "type": FIELDS[name]["type"], "options": FIELDS[name].get("options")}
            for name in required(fields, rules) if fields.get(name) in (None, "", [])]


def filed_title(fields: dict) -> str:
    """The name answers cite: "Meeting · Acme · 2026-10-12 · Kickoff", so a quote always says where it came from."""
    where = fields.get("about_name") or "Company"
    label = "Meeting" if fields["kind"] == "meeting" else KINDS[fields["kind"]]
    topic = fields.get("topic") or fields["title"]
    return " · ".join([label, where, fields["date"], topic])


def header(fields: dict) -> str:
    """The first lines of the filed text, so every reader knows what this is and how far to trust it."""
    lines = [f"{filed_title(fields)}.", f"Owner: {fields['owner']}."]
    if fields["kind"] == "meeting":
        lines.append(f"{MEETING_TYPES[fields['meeting_type']]}. Attended by {', '.join(fields['attendees'])}.")
        lines.append("This is a record of what was said in a meeting, not a company rule.")
    if fields.get("parties"):
        lines.append(f"Parties: {', '.join(fields['parties'])}.")
    return "\n".join(lines)


def tagged(text: str) -> str:
    """A meeting transcript with each spoken line marked [Agreed], [Action], [Suggested] or [Discussed]."""
    out = []
    for line in text.splitlines():
        if not line.strip():
            out.append(line)
            continue
        tag = next((name for name, pattern in LINE_TAGS if pattern.search(line)), "Discussed")
        out.append(f"[{tag}] {line}")
    return "\n".join(out)
