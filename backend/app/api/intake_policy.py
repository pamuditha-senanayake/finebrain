# intake_policy.py: what every document must say about itself before it joins the knowledge base, and how the intake
# agent (Lisena) asks for what is missing. One source of truth: the schema, the policy, the skill steps and the questions
# all live here, and the console shows them as they are. Used by: intake.py, tests/test_intake.py.
import re
from datetime import date

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
LINE_TAGS = [  # first match wins; a meeting line with none of these is Discussed
    ("Agreed", re.compile(r"\b(agreed|we agree|decided|decision|confirmed|signed off|approved)\b", re.I)),
    ("Action", re.compile(r"\b(action item|to ?do|will send|will share|will follow up|by (monday|tuesday|wednesday|thursday|friday|next week|tomorrow)|owner:)\b", re.I)),
    ("Suggested", re.compile(r"\b(suggest\w*|propos\w*|maybe|could we|what if|idea|recommend\w*)\b", re.I)),
]


def required(fields: dict) -> list[str]:
    """The fields this document must have, in the order Lisena asks for them."""
    kind, about = fields.get("kind"), fields.get("about")
    needed = []
    for name, spec in FIELDS.items():
        rule = spec["for"]
        if rule == "*" or rule == kind or (rule == "client_or_project" and about in ("client", "project")):
            needed.append(name)
    return needed


def clean(name: str, value) -> object | None:
    """The value as stored, or None when it does not answer the field (an unknown choice, a bad date, an empty list)."""
    spec = FIELDS.get(name)
    if spec is None or value is None:
        return None
    if spec["type"] == "list":
        items = value if isinstance(value, list) else str(value).split(",")
        names = [str(item).strip() for item in items if str(item).strip()]
        return names or None
    text = str(value).strip()
    if spec["type"] == "choice":
        return text if text in spec["options"] else None
    if spec["type"] == "date":
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return None
    return text[:200] or None


def missing(fields: dict) -> list[dict]:
    """One question per required field still empty: what Lisena asks next, first one first."""
    return [{"field": name, "question": FIELDS[name]["ask"], "type": FIELDS[name]["type"], "options": FIELDS[name].get("options")}
            for name in required(fields) if fields.get(name) in (None, "", [])]


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
