# activities.py: the activity alphabet of a skill's runs (Research Lab P3), so a run's story is an event log process mining
# can read. Every run step names one activity: the context read, the action proposed, the access decision, the wait for a
# person, the action done; a skill's alphabet is those activities for the tools it may use. Steps recorded before P3 carry
# none, and the export derives theirs the same way (a tool step then cannot say which tool, so it reads act_unknown).
# Used by: run_steps.py (make_step), run_finish.py, stages_orchestrate.py, event_log.py, research/conformance.py. Uses: tools.py.
from app.pipeline.tools import TOOLS

# Config
FIXED = ["retrieve_context", "context_unavailable", "not_started", "access_allow", "access_deny", "await_approval"]


def activity_of(kind: str, decision: str, action_type: str | None = None) -> str:
    """The activity a step stands for, from what the step is and what it decided."""
    if kind == "retrieval":
        return "context_unavailable" if decision == "context_unavailable" else "retrieve_context"
    if kind == "judgment":
        return f"propose_{decision}" if decision in TOOLS else "not_started"  # S4's step_00 records why the run could not start
    if kind == "access_check":
        return f"access_{decision}"
    if kind == "human":
        return "await_approval"
    if kind == "tool":
        return f"act_{action_type or 'unknown'}" + ("" if decision == "succeeded" else f"_{decision}")
    return kind


def alphabet(skill: dict) -> list[str]:
    """Every activity a run of this skill can show: the fixed ones, then proposing and doing each tool it may use."""
    tools = skill.get("allowed_tools") or []
    return FIXED + [f"propose_{t}" for t in tools] + [f"act_{t}" for t in tools] + [f"act_{t}_failed" for t in tools]
