# stages_reason.py: S6 Reason (task and bundle to K5). S5 Retrieve lives in stages_retrieve.py.
# Used by: run_steps.py, tests. Uses: contracts_signal.py, contracts_reason.py, fakes.py (Model type).
from app.pipeline.contracts_reason import ContextBundle, ModelUsage, ProposedAction
from app.pipeline.contracts_signal import Money, TaskRequest, Touches
from app.pipeline.fakes import Model

# Config
PROPOSE_PROMPT = "propose_action"
MONEY_ACTIONS = {"issue_refund", "apply_credit"}


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
