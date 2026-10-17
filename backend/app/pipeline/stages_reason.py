# stages_reason.py: S5 Retrieve (K4 query to K4 bundle) and S6 Reason (task and bundle to K5).
# Used by: tests/test_stages.py. Uses: contracts_signal.py, contracts_reason.py, fakes.py (Model type).
# Step 2 retrieval is rule based. Voyage embeddings and rerank come when stages get thicker (step 7).
from app.pipeline.contracts_reason import (
    ContextBundle, ContextItem, ContextQuery, DeniedReason, ModelUsage, ProposedAction,
)
from app.pipeline.contracts_signal import Money, TaskRequest, Touches
from app.pipeline.fakes import Model

# Config
ALL_SENSITIVITIES = {"public", "internal", "confidential", "restricted"}
READABLE_BY_TIER = {  # restricted needs a human above L3
    "L1": ALL_SENSITIVITIES,
    "L2": ALL_SENSITIVITIES,
    "L3": {"public", "internal", "confidential"},
}
SENSITIVITY_RULE_ID = "sensitivity_by_tier"
PROPOSE_PROMPT = "propose_action"
MONEY_ACTIONS = {"issue_refund", "apply_credit"}


# --- S5 Retrieve

def is_relevant(item: dict, query: ContextQuery) -> bool:
    """Policies of the asked kinds always count; facts only when they name an entity in the query."""
    if query.node_types is not None and item["kind"] not in query.node_types:
        return False
    if item["kind"] == "policy":
        return True
    return any(ref in item["text"] for ref in query.entity_refs)


def retrieve(query: ContextQuery, knowledge: list[dict], new_id) -> ContextBundle:
    """S5: return relevant items the principal may read. Denied items are counted, never shown."""
    # Step 1: keep only relevant items
    relevant = [item for item in knowledge if is_relevant(item, query)]

    # Step 2: split by what the principal's tier may read
    readable = READABLE_BY_TIER.get(query.principal.tier, set())  # unknown tier reads nothing
    allowed = [item for item in relevant if item["sensitivity"] in readable]
    denied_count = len(relevant) - len(allowed)

    # Step 3: build the bundle, capped at top_k
    return ContextBundle(
        items=[ContextItem.model_validate(item) for item in allowed[: query.top_k]],
        denied_count=denied_count,
        denied_reasons=[DeniedReason(rule_id=SENSITIVITY_RULE_ID, count=denied_count)] if denied_count else [],
        access_decision_ids=[new_id("acc")],
        latency_ms=0,
    )


# --- S6 Reason

def propose(
    task: TaskRequest, bundle: ContextBundle, model: Model, run_id: str, step_id: str, cluster_id: str,
) -> ProposedAction:
    """S6: ask the model for one action and wrap its answer as K5."""
    # Step 1: the model sees only the task and the bundle it was allowed
    context = {
        "task": task.model_dump(mode="json"),
        "items": [item.model_dump(mode="json") for item in bundle.items],
    }
    answer = model(PROPOSE_PROMPT, context)

    # Step 2: money and touches come from the action itself, not from the model's claim
    amount = answer["arguments"].get("amount")
    touches = Touches(
        money=answer["action_type"] in MONEY_ACTIONS, personal_data=False,
        public_content=False, legal_tax=False, clusters=[cluster_id],
    )
    return ProposedAction(
        run_id=run_id, step_id=step_id, action_type=answer["action_type"], tool_id=answer["tool_id"],
        tool_version=answer["tool_version"], arguments=answer["arguments"],
        money=Money(**amount) if amount else None, touches=touches,
        rationale_summary=answer["rationale_summary"], citations=answer["citations"],
        model=ModelUsage(**answer["usage"]), confidence=answer["confidence"],
    )
