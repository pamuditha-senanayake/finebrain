# retrieve_scope.py: step 13b, narrow first. Turns a case's entities into a search scope (the things it is about, plus what
# their typed links reach in at most two hops), and lists the levels S5 widens through when a level finds too little.
# Used by: stages_retrieve.py (ladder), run_steps.py (S6 runs), api/ask.py (questions). Uses: item_tags.py, a registry (store_entities.py).
from app.pipeline import item_tags
from app.pipeline.contracts_reason import ContextQuery

# Config
HOPS = 2  # typed links followed at most this far; free wandering is what makes cost grow
MOST_ENTITIES = 50  # a scope never holds more, so a very connected customer cannot widen it to everything
WIDEN_BELOW = 3  # fewer candidates than this at one level, and S5 tries the next wider one


# --- Building the scope

def linked(entities, entity_ids: list[str], hops: int = HOPS) -> list[str]:
    """The entities themselves, then what their typed links reach, nearest first. Unknown ids are dropped."""
    found = [entity_id for entity_id in dict.fromkeys(entity_ids) if entities.get(entity_id)]
    frontier = list(found)
    for _ in range(hops):
        reached = [other for entity_id in frontier for link in entities.links_of(entity_id) for other in (link["from_id"], link["to_id"])]
        frontier = [entity_id for entity_id in dict.fromkeys(reached) if entity_id not in found]
        found += frontier
    return found[:MOST_ENTITIES]


def entities_in_question(lane, question: str) -> list[str]:
    """The known things a question names, and their links. The question is not masked, so only payments match today."""
    named = item_tags.entities_in_text(question, item_tags.customer_check(lane.entities))
    return linked(lane.entities, named)


# --- Widening

def ladder(query: ContextQuery) -> list[tuple[str, dict]]:
    """The levels to search, narrowest first: these things in these domains, then the domains, then the whole tenant."""
    levels = []
    if query.entity_ids:
        levels.append(("entity", {"domains": query.domains, "entity_ids": query.entity_ids}))
    if query.domains:
        levels.append(("domain", {"domains": query.domains, "entity_ids": []}))
    levels.append(("tenant", {"domains": [], "entity_ids": []}))
    return levels
