# intake_talk.py: adding a document as a chat with Lisena. Each typed or spoken reply is read as one of: an answer to the
# question she asked, a change ("change the owner to Nimal"), a yes to file it, or stop. What she says back is written
# here too, so the chat, the voice and the tests all hear the same words. Rules only: no model call per reply.
# Used by: intake.py. Uses: intake_policy.py.
import re

from app.api import intake_policy as policy

# Config
LABELS = {  # the words people use for each field, for "change the X to Y"
    "kind": ["kind", "type of document", "document type"], "title": ["name", "title"], "date": ["date", "day"],
    "about": ["about"], "about_name": ["client", "project", "client name", "project name"], "owner": ["owner"],
    "meeting_type": ["meeting type", "type of meeting", "meeting"], "attendees": ["attendees", "people", "who attended", "attended"],
    "topic": ["topic", "subject"], "parties": ["parties"], "vendor": ["vendor", "payee", "paid to", "supplier"],
    "amount": ["amount", "total", "price", "cost"], "currency": ["currency"], "category": ["category", "type of spend"], "repeats": ["repeats", "repeat", "frequency"],
}
SHOWN = {"kind": "Kind", "title": "Name", "date": "Date", "about": "About", "about_name": "Client or project", "owner": "Owner",
         "meeting_type": "Meeting", "attendees": "Attended", "topic": "Topic", "parties": "Parties", "vendor": "Paid to", "amount": "Amount",
         "currency": "Currency", "category": "For", "repeats": "Repeats"}
CHANGE = re.compile(r"^(?:please\s+)?(?:change|set|make|update|correct|fix|edit)\s+(?:the\s+)?(?P<label>[a-z ]+?)\s+(?:to|as|is|=)\s+(?P<value>.+)$", re.I)
YES = re.compile(r"^(yes|yeah|yep|sure|ok(ay)?|confirm(ed)?|go ahead|do it|add it|file it|looks good|correct|that'?s right|save( it)?)\b", re.I)
STOP = re.compile(r"^(cancel|stop|never ?mind|forget it|don'?t add|abort)\b", re.I)
FILLER = re.compile(r"^(it'?s|it is|it was|its|this is|that is|about|the|on|they are|we had)\s+", re.I)


def field_of(label: str) -> str | None:
    said = label.strip().lower()
    return next((name for name, words in LABELS.items() if said in words), None)


def understand(text: str, asking: str | None) -> tuple[str, dict]:
    """("change" | "answer", fields), ("yes" | "stop" | "unclear", {}). A change names its field; an answer fills the open question."""
    said = text.strip().rstrip(".!")
    if STOP.match(said):
        return "stop", {}
    if (found := CHANGE.match(said)) and (name := field_of(found.group("label"))):
        value = policy.clean(name, found.group("value"))
        return ("change", with_currency(name, found.group("value"), {name: value})) if value is not None else ("unclear", {})
    if asking:
        answer = said
        while FILLER.match(answer):
            answer = FILLER.sub("", answer, count=1)
        value = policy.clean(asking, answer)
        if value is not None and not (YES.match(said) and policy.FIELDS[asking]["type"] != "text"):
            return "answer", with_currency(asking, answer, {asking: value})
    if YES.match(said):
        return "yes", {}
    return "unclear", {}


def with_currency(name: str, said: str, fields: dict) -> dict:
    """ "49 dollars" answers the amount and the currency at once."""
    currency = policy.money(said)[1] if name == "amount" else None
    return {**fields, "currency": currency} if currency else fields


def shown(name: str, value) -> str:
    if isinstance(value, list):
        return ", ".join(value)
    if name == "amount":
        return f"{value:,.2f}"
    return (policy.FIELDS[name].get("options") or {}).get(value, str(value))


def summary(fields: dict) -> str:
    return "; ".join(f"{SHOWN[name]}: {shown(name, fields[name])}" for name in SHOWN if fields.get(name) not in (None, "", []))


def ask(question: dict) -> str:
    options = question.get("options")
    return question["question"] + (f" ({', '.join(options.values())})" if options else "")


def opening(fields: dict, questions: list[dict]) -> str:
    """What Lisena says once the file is read: what she found, then the first thing she needs."""
    found = []
    if fields.get("kind"):
        found.append(f"a {policy.KINDS[fields['kind']].lower()}")
    if fields.get("date"):
        found.append(f"from {fields['date']}")
    if fields.get("attendees"):
        found.append(f"with {', '.join(fields['attendees'])}")
    if fields.get("about_name"):
        found.append(f"about {fields['about_name']}")
    if fields.get("topic"):
        found.append(f"on {fields['topic']}")
    if fields.get("amount"):
        found.append(f"for {fields.get('currency', '')} {fields['amount']:,.2f}".replace("for  ", "for "))
    if fields.get("vendor"):
        found.append(f"paid to {fields['vendor']}")
    said = f"I read it. It looks like {' '.join(found)}. " if found else "I read it. "
    return said + (ask(questions[0]) if questions else ready(fields))


def ready(fields: dict) -> str:
    return f"Here is what I have. {summary(fields)}. Shall I add it to the knowledge base? You can also say, for example, change the owner to Nimal."


def reply(intent: str, fields: dict, questions: list[dict], asking: str | None) -> str:
    """Lisena's next words after one reply."""
    if intent == "unclear":
        if asking:
            return f"Sorry, that does not answer it. {ask(next(q for q in questions if q['field'] == asking))}"
        return "Sorry, I did not catch that. Say yes to add it, or say what to change, like change the date to 12 October."
    if questions:
        prefix = "Changed. " if intent == "change" else "Got it. " if intent == "answer" else "I still need one more thing. " if intent == "yes" else ""
        return prefix + ask(questions[0])
    return ("Changed. " if intent == "change" else "") + ready(fields)
