# small_talk.py: a greeting, thanks or goodbye is answered at once, with no search and no model call, so "hi" never lists
# documents and a spoken back and forth stays fast. Anything with a real question in it goes on to the full answer.
# Used by: ask.py.
import re

# Config
NAME = r"(?: (?:there|lisena|brain|everyone|again))?"
GREETING = r"(?:hi|hello|hey|hiya|yo|good (?:morning|afternoon|evening|day))"
HOW = r"(?:how are you(?: doing)?(?: today)?|how is it going|hows it going|how is your day|whats up|what is up)"
THANKS = r"(?:(?:ok |okay |great |perfect )?(?:thanks|thank you|cheers)(?: so much| a lot)?(?: lisena)?)"
BYE = r"(?:(?:ok |okay )?(?:bye|goodbye|bye for now|see you|see you later|good night|talk later)(?: lisena)?)"
REPLIES = [
    (re.compile(rf"(?:{GREETING}{NAME} )?{HOW}{NAME}"), "I am well, {address}, and ready to help. What do you need?"),
    (re.compile(rf"{GREETING}{NAME}"), "Hi {address}. How can I help you today?"),
    (re.compile(THANKS), "You are welcome, {address}."),
    (re.compile(BYE), "Goodbye, {address}. I am here when you need me."),
]


def normalized(text: str) -> str:
    """Lower case, no punctuation or apostrophes, single spaces: "Hi, Lisena!" reads as "hi lisena"."""
    return " ".join(re.sub(r"[^a-z ]", "", text.lower().replace("'", "")).split())


def reply(question: str, address: str) -> str | None:
    """The quick reply when the whole message is small talk; None when it asks for something."""
    said = normalized(question)
    return next((answer.format(address=address) for pattern, answer in REPLIES if pattern.fullmatch(said)), None)
