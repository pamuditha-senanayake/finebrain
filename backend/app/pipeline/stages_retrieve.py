# stages_retrieve.py: S5 Retrieve (K4 query to K4 bundle). Hybrid search (meaning + exact words), as-of time,
# access by tier and on_behalf_of, rerank, and a token budget. Denied items are counted, never shown.
# Used by: run_steps.py, tests. Uses: contracts_reason.py, observe.py, a chunks store (store_chunks.py), embed and rerank.
from app.pipeline.contracts_reason import AccessDecision, ContextBundle, ContextItem, ContextQuery, DeniedReason
from app.pipeline.observe import count, log_event

# Config
ALL_SENSITIVITIES = {"public", "internal", "confidential", "restricted"}
READABLE_BY_TIER = {"L1": ALL_SENSITIVITIES, "L2": ALL_SENSITIVITIES, "L3": {"public", "internal", "confidential"}}
ALL_KINDS = ["fact", "policy", "chunk", "skill_step"]
SENSITIVITY_RULE_ID = "sensitivity_by_tier"
CANDIDATES_PER_LIST = 20
RRF_K = 60  # reciprocal rank fusion constant: rank 1 scores 1/61, rank 2 scores 1/62, ...
CHARS_PER_TOKEN = 4  # rough budget estimate, enough to keep bundles under max_tokens


class ContextUnavailable(Exception):
    """The knowledge store could not be searched. S4 retries once, then escalates."""
    retryable = True


# --- Finding candidates

def embed_query(embed, text: str) -> list[float] | None:
    """The query's vector, or None so search falls back to exact words only."""
    try:
        return embed([text], "query")[0]
    except Exception as error:  # a down embedding service degrades search, it does not stop the run
        count("s5.degraded")
        log_event("S5", "degraded", error=type(error).__name__)
        return None


def fuse(ranked_lists: list[list[dict]]) -> list[tuple[dict, float]]:
    """Reciprocal rank fusion: items high in either list rise; items high in both rise most."""
    scores, items = {}, {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item["item_id"]] = scores.get(item["item_id"], 0.0) + 1 / (RRF_K + rank)
            items[item["item_id"]] = item
    return sorted(((items[item_id], score) for item_id, score in scores.items()), key=lambda pair: -pair[1])


def find_candidates(query: ContextQuery, chunks, embed, valid, recorded) -> list[tuple[dict, float]]:
    """Exact-word and meaning search over items true at `valid` and known at `recorded`."""
    kinds, text = query.node_types or ALL_KINDS, " ".join([query.query_text, *query.entity_refs])
    ranked_lists = [chunks.by_text(text, kinds, valid, recorded, CANDIDATES_PER_LIST)]
    vector = embed_query(embed, text)
    if vector is not None:
        ranked_lists.append(chunks.by_vector(vector, kinds, valid, recorded, CANDIDATES_PER_LIST))
    return fuse(ranked_lists)


# --- Filtering and ordering

def is_relevant(item: dict, query: ContextQuery) -> bool:
    """A fact is about a specific thing, so it counts only when it names an entity in the query.
    That also keeps one customer's payment out of another customer's run."""
    return item["kind"] != "fact" or any(ref in item["text"] for ref in query.entity_refs)


def readable_for(query: ContextQuery, people: dict) -> set[str]:
    """What the principal may read; acting for a person, only what both may read. Unknown person reads nothing."""
    agent = READABLE_BY_TIER.get(query.principal.tier, set())
    if query.on_behalf_of is None:
        return agent
    person = people.get(query.on_behalf_of)
    return agent & READABLE_BY_TIER.get(person["tier"], set()) if person else set()


def rerank_items(query: ContextQuery, scored: list[tuple[dict, float]], rerank) -> list[tuple[dict, float]]:
    """Order by the reranker's relevance. If it fails, keep the fused order."""
    if not scored:
        return scored
    try:
        relevance = rerank(query.query_text, [item["text"] for item, _ in scored])
    except Exception as error:
        count("s5.rerank_skipped")
        log_event("S5", "rerank_skipped", error=type(error).__name__)
        return scored
    return sorted(((item, score) for (item, _), score in zip(scored, relevance)), key=lambda pair: -pair[1])


def fit_budget(scored: list[tuple[dict, float]], top_k: int, max_tokens: int) -> list[tuple[dict, float]]:
    """Keep the best items until top_k or the token budget is reached."""
    kept, used = [], 0
    for item, score in scored[:top_k]:
        cost = len(item["text"]) // CHARS_PER_TOKEN + 1
        if used + cost > max_tokens:
            break
        kept.append((item, score))
        used += cost
    return kept


# --- S5 Retrieve

def retrieve(query: ContextQuery, chunks, embed, rerank, people: dict, new_id, now) -> tuple[ContextBundle, AccessDecision]:
    """S5: the bundle the principal may see, and one access decision for the audit log."""
    # Step 1: candidates true and known at the asked time
    try:
        candidates = find_candidates(query, chunks, embed, query.as_of_valid or now, query.as_of_recorded or now)
    except Exception as error:
        raise ContextUnavailable(type(error).__name__) from None

    # Step 2: relevant, then readable; withheld items are only counted
    relevant = [(item, score) for item, score in candidates if is_relevant(item, query)]
    readable = readable_for(query, people)
    allowed = [(item, score) for item, score in relevant if item["sensitivity"] in readable]
    denied = len(relevant) - len(allowed)

    # Step 3: best first, within budget
    kept = fit_budget(rerank_items(query, allowed, rerank), query.top_k, query.max_tokens)
    decision = AccessDecision(decision_id=new_id("acc"), decision="allow", rule_id=SENSITIVITY_RULE_ID, reason=f"{len(kept)} shown, {denied} withheld", latency_ms=0)
    bundle = ContextBundle(
        items=[ContextItem.model_validate({**item, "score": round(score, 4)}) for item, score in kept],
        denied_count=denied, denied_reasons=[DeniedReason(rule_id=SENSITIVITY_RULE_ID, count=denied)] if denied else [],
        access_decision_ids=[decision.decision_id], latency_ms=0,
    )
    return bundle, decision
