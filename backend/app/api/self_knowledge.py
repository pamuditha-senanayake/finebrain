# self_knowledge.py: the brain's knowledge about itself, for the cold start. Each "## " section of
# samples/brain_self_knowledge.md becomes one public knowledge item; "Who I am" goes with every question.
# Used by: hq.py (adds the items to the seed), ask.py (the overview). Uses: contracts_reason.py.
from functools import cache
from pathlib import Path

from app.pipeline.contracts_reason import ContextItem

# Config
SOURCE = Path(__file__).resolve().parents[2] / "samples" / "brain_self_knowledge.md"
DOCUMENT_ID = "doc_brain_self"
WRITTEN_AT = "2026-10-18T00:00:00+05:30"
OVERVIEW_ID = "self_who_i_am"


def slug(title: str) -> str:
    return "self_" + "_".join(word for word in "".join(c if c.isalnum() else " " for c in title.lower()).split())


@cache
def items() -> tuple[dict, ...]:
    """One knowledge item per section, in the seed's knowledge shape."""
    text = SOURCE.read_text()
    found, at = [], text.find("\n## ")
    while at != -1:
        end = text.find("\n## ", at + 1)
        section = text[at + 1 : end if end != -1 else len(text)].strip()
        title, _, body = section.removeprefix("## ").partition("\n")
        found.append({
            "item_id": slug(title), "kind": "chunk", "text": f"{title}. {body.strip()}",
            "source": {"document_id": DOCUMENT_ID, "uri": "samples/brain_self_knowledge.md", "span": f"{at + 1}:{end if end != -1 else len(text)}"},
            "valid_from": WRITTEN_AT, "valid_to": None, "recorded_at": WRITTEN_AT, "verified_by": "finebrain", "version_ref": None,
            "score": 0.0, "sensitivity": "public",
        })
        at = end
    return tuple(found)


def overview() -> ContextItem:
    """'Who I am': always offered, so a first question like "what can you do?" has something true to stand on."""
    return ContextItem.model_validate(next(item for item in items() if item["item_id"] == OVERVIEW_ID))
