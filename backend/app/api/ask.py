# ask.py: Ask the Brain for Finebase HQ. A person's question goes through S5 with that person's own rights, then Claude
# answers from only the documents they may read, plus the brain's own "who I am", and what was said earlier in the
# conversation. Each turn is remembered. Without a Claude key it lists the closest documents.
# Used by: routes.py, tests/test_api_brain.py. Uses: ask_memory.py, self_knowledge.py, retrieve_scope.py, stages_retrieve.py, retry.py.
from app.api import ask_memory, search, self_knowledge
from app.api.ui_models_work import AskAnswer, Citation, LookedIn
from app.pipeline import retrieve_scope, stages_retrieve
from app.pipeline.contracts_reason import ContextItem, ContextQuery
from app.pipeline.contracts_signal import Principal
from app.pipeline.retry import call_with_retry

# Config
ASK_TOP_K = 6
ASK_MAX_TOKENS = 3000
LABEL_CHARS = 80
NO_CLAUDE_NOTE = "Claude is off, so here are the closest documents."
NOTHING_FOUND = "Nothing you can read answers this yet."
PAGE_VIEW_ID = "page_view"
PAGE_VIEW_CHARS = 6000  # what is on screen, capped; the console already trims to about 4000


class AskUnavailable(Exception):
    """The knowledge store could not be read, even after one retry."""


def citation(item: ContextItem) -> Citation:
    first_line = item.text.strip().splitlines()[0] if item.text.strip() else item.item_id
    href = item.source.uri if item.item_id == PAGE_VIEW_ID else f"/l2/policies/{item.version_ref.id}" if item.kind == "policy" and item.version_ref else "/l2/library"
    return Citation(id=item.item_id, kind=item.kind, label=first_line[:LABEL_CHARS], href=href,
                    valid_from=(item.valid_from or item.recorded_at).isoformat(), valid_to=item.valid_to.isoformat() if item.valid_to else None)


def page_item(lane, page: dict | None) -> ContextItem | None:
    """What the person sees right now, as one more document. It is data from the screen, never instructions."""
    seen = ((page or {}).get("snapshot") or "").strip()
    if not seen:
        return None
    title = (page.get("title") or "this page").strip()
    return ContextItem(item_id=PAGE_VIEW_ID, kind="chunk", text=f"The page on screen now: {title} ({page.get('path', '')}).\n{seen[:PAGE_VIEW_CHARS]}",
                       source={"document_id": PAGE_VIEW_ID, "uri": page.get("path", "")}, valid_from=lane.now, valid_to=None, recorded_at=lane.now,
                       verified_by=None, version_ref=None, score=1.0, sensitivity="internal")


def address_of(person: dict) -> str:
    """How the brain addresses this person: their chosen form, like "sir", or else their first name."""
    return person.get("address") or person.get("name", "").split(" ")[0] or "there"


def read_for(lane, persona: str, question: str):
    """S5 as the person, narrowed to the things the question names: their tier decides what they may read. The access decision goes to the audit log."""
    person = lane.seed["people"][persona]
    query = ContextQuery(run_id=lane.new_id("ask"), principal=Principal(type="human", id=persona, capabilities=["kb.read"], tier=person["tier"]),
                         on_behalf_of=None, query_text=question, branch="main", top_k=ASK_TOP_K, max_tokens=ASK_MAX_TOKENS,
                         entity_ids=retrieve_scope.entities_in_question(lane, question))  # narrow to what it names; every domain
    try:
        bundle, decision = call_with_retry(
            lambda: stages_retrieve.retrieve(query, lane.chunks, lane.embed, lane.rerank, lane.seed["people"], lane.new_id, lane.now),
            lambda error: isinstance(error, stages_retrieve.ContextUnavailable), attempts=2, base_delay=0.2,
        )
    except stages_retrieve.ContextUnavailable:
        raise AskUnavailable() from None
    lane.bus.publish("access.decisions", "access.decided", decision, "ask")
    return bundle


def ask(lane, answerer, persona: str, question: str, scope: str | None, conversation_id: str | None, page: dict | None = None) -> AskAnswer:
    """The answer, its citations, and how many items were withheld. A missing conversation id starts a new one."""
    conversation_id = conversation_id or lane.new_id("conv")
    history = ask_memory.recent(lane, conversation_id, persona)
    bundle = read_for(lane, persona, question)
    by_id = {item.item_id: item for item in bundle.items}
    if answerer is None:
        text, cited = (NO_CLAUDE_NOTE, list(by_id)) if by_id else (NOTHING_FOUND, [])
    else:
        by_id.setdefault(self_knowledge.OVERVIEW_ID, self_knowledge.overview())
        if (on_screen := page_item(lane, page)) is not None:
            by_id[PAGE_VIEW_ID] = on_screen
        text, cited = answerer(question, [(item.item_id, item.text) for item in by_id.values()], history, address_of(lane.seed["people"][persona]))
    cited = [item_id for item_id in cited if item_id in by_id]
    ask_memory.remember(lane, conversation_id, persona, question, text, cited)
    return AskAnswer(question=question, answer=text, citations=[citation(by_id[item_id]) for item_id in cited], withheld=bundle.denied_count,
                     scope=scope, conversation_id=conversation_id, actions=search.show_me(lane, [by_id[item_id] for item_id in cited], question) or None,
                     looked_in=LookedIn(**bundle.scope.model_dump()) if bundle.scope else None)
