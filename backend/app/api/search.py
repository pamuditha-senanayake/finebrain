# search.py: step 11, find. One search over runs, documents, policies and skills. Each hit
# says where to go and what to light up there: a focus (kind, id, and the sentence span when the match is in a text).
# Used by: routes.py. Uses: lists_rows.py, graph_views.py (place_in_document), the lane's search index.
import re
from urllib.parse import urlencode

from app.api import lists_rows
from app.api.graph_views import ACCESS_BY_TIER, place_in_document
from app.api.ui_models import UiModel
from app.pipeline.stages_file import SENSITIVITY_ORDER

# Config
PER_KIND = 5
MOST = 24
TEXT_KINDS = ["chunk", "policy"]
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
SNIPPET_CHARS = 110


class Focus(UiModel):
    kind: str
    id: str
    field: str | None = None
    span: tuple[int, int] | None = None


class SearchHit(UiModel):
    id: str
    kind: str
    label: str
    href: str
    hint: str
    focus: Focus | None = None


def words_of(q: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", q.lower())


def sentence_span(text: str, words: list[str]) -> tuple[int, int] | None:
    """Where the first sentence that holds a query word starts and ends in `text`."""
    start = 0
    for end in [*(m.start() for m in SENTENCE_END.finditer(text)), len(text)]:
        if any(word in text[start:end].lower() for word in words):
            return start, end
        start = next((m.end() for m in SENTENCE_END.finditer(text) if m.start() == end), end)
    return None


def hit(kind: str, item_id: str, label: str, path: str, hint: str, focus: Focus, words: list[str], extra: dict | None = None) -> dict:
    """The link carries the focus, so any page can light it up: ?focus=kind:id&span=a:b."""
    params = {**(extra or {}), "focus": f"{focus.kind}:{focus.id}", **({"span": f"{focus.span[0]}:{focus.span[1]}"} if focus.span else {}), "q": " ".join(words)}
    return SearchHit(id=item_id, kind=kind, label=label[:90], href=f"{path}?{urlencode(params)}", hint=hint[:SNIPPET_CHARS], focus=focus).ui()


def run_hits(lane, words: list[str]) -> list[dict]:
    found = [row for row in lists_rows.runs(lane) if all(w in f"{row['id']} {row['subject']} {row['agentId']}".lower() for w in words)]
    return [hit("Run", row["id"], row["subject"], "/l3/runs", row["status"].replace("_", " "), Focus(kind="run", id=row["id"]), words) for row in found[:PER_KIND]]


def text_hit(lane, item: dict, words: list[str]) -> dict | None:
    """One sentence in an uploaded document or in policy wording, as a hit that lights that sentence."""
    record = lane.records.load("document", item["source"]["document_id"])
    ref = item.get("version_ref")
    if item["kind"] == "policy" and ref:
        mine = sorted((k for k in lane.graph.latest("knowledge") if (k.get("version_ref") or {}).get("id") == ref["id"] and k["version_ref"]["version"] == ref["version"]), key=place_in_document)
        ids = [k["item_id"] for k in mine]
        before = sum(len(k["text"]) + 1 for k in mine[: ids.index(item["item_id"])]) if item["item_id"] in ids else 0
        local = sentence_span(item["text"], words) or (0, len(item["text"]))
        focus = Focus(kind="policy", id=ref["id"], span=(before + local[0], before + local[1]))
        return hit("Policy", item["item_id"], ref["id"].replace("_", " "), f"/l2/policies/{ref['id']}", item["text"][local[0]:local[1]], focus, words)
    if record:
        text = item["text"].removeprefix(f"{record['title']}: ")
        span = sentence_span(text, words)
        return hit("Document", item["item_id"], record["title"], "/l2/library", text[span[0]:span[1]] if span else text, Focus(kind="chunk", id=item["item_id"], span=span), words, {"doc": record["document_id"]})
    return None


def readable(lane, persona: str, item: dict) -> bool:
    """Only what this person's tier may read, the same ceiling Ask uses."""
    ceiling = ACCESS_BY_TIER.get(lane.seed["people"][persona]["tier"], "public")
    return SENSITIVITY_ORDER.index(item.get("sensitivity", "internal")) <= SENSITIVITY_ORDER.index(ceiling)


def text_hits(lane, persona: str, words: list[str], q: str) -> list[dict]:
    """Sentences found by the same index Ask reads."""
    found = [text_hit(lane, item, words) for item in lane.chunks.by_text(q, TEXT_KINDS, lane.now, lane.now, 12) if readable(lane, persona, item)]
    return [found_hit for found_hit in found if found_hit][:PER_KIND * 2]


def show_me(lane, items: list, question: str) -> list[dict]:
    """The Ask answer's one "Show me": the first cited sentence that lives in a document or policy page."""
    words = words_of(question)
    for item in items:
        found = text_hit(lane, item.model_dump(mode="json"), words) if words else None
        if found:
            return [{"label": "Show me", "href": found["href"]}]
    return []


def skill_hits(lane, words: list[str]) -> list[dict]:
    found = [s for s in lane.graph.latest("skill") if all(w in f"{s['id']} {s.get('name', '')}".lower() for w in words)]
    return [hit("Skill", s["id"], s.get("name") or s["id"], f"/l2/skills/{s['id']}", s.get("trigger", ""), Focus(kind="skill", id=s["id"]), words) for s in found[:PER_KIND]]


def search(lane, persona: str, q: str) -> list[dict]:
    """Up to MOST hits: wording first, then skills, conversations and runs."""
    words = words_of(q)
    if len(q.strip()) < 2 or not words:
        return []
    return [*text_hits(lane, persona, words, q), *skill_hits(lane, words), *run_hits(lane, words)][:MOST]
