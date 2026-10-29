# ask_graph.py: what Lisena knows about how the work is organized, straight from the graph Workflow Studio writes:
# each workflow (an activity) with its status, owner agent and that agent's rights, its skill and tools, its policies and
# the connections it listens to. One item per question, so "who handles refunds?" or "what may the landing assistant do?"
# is answered from the live graph, never from memory. Used by: ask.py. Uses: studio_state.py, studio_activity.py.
from app.api.studio_state import Studio
from app.pipeline.contracts_reason import ContextItem

# Config
WORK_MAP_ID = "work_map"
WORK_MAP_URI = "/studio"


def workflow_line(st: Studio, flow: dict) -> str:
    """One workflow in plain words: who owns it, how it works, what limits it, what wakes it."""
    members = st.members(flow)
    names = lambda kind: [m for m in members if m["kind"] == kind]  # noqa: E731
    agents = [f"{a['name']} (may: {', '.join(a['fields'].get('capabilities') or []) or 'nothing yet'})" for a in names("agent")]
    skills = [f"{s['name']} (tools: {', '.join(t.removeprefix('tool:').replace('_', ' ') for t in s['fields'].get('tools') or []) or 'none'})" for s in names("skill")]
    sources = [st.sources.get(s["fields"].get("source"), {}).get("name") or s["fields"].get("source") or "nothing" for s in names("sensor")]
    return (f"Workflow {flow['name']} ({flow['status']}): {flow.get('description') or 'no description'}. Owner: {', '.join(agents) or 'none yet'}. "
            f"Skill: {', '.join(skills) or 'none yet'}. Policies: {', '.join(p['name'] for p in names('policy')) or 'none'}. "
            f"Listens to: {', '.join(sources) or 'nothing yet'}.")


def work_map(lane) -> ContextItem | None:
    """Every workflow, as one readable item. None when there are none, or the graph cannot be read now."""
    try:
        st = Studio.of(lane)
    except Exception:  # Ask still answers from the documents; the graph part is left out, never guessed
        return None
    if not st.flows:
        return None
    lines = [workflow_line(st, flow) for flow in sorted(st.flows.values(), key=lambda f: f["name"])]
    return ContextItem(item_id=WORK_MAP_ID, kind="fact", text="How the work is organized now (Workflow Studio's graph):\n" + "\n".join(lines),
                       source={"document_id": WORK_MAP_ID, "uri": WORK_MAP_URI}, valid_from=lane.now, valid_to=None, recorded_at=lane.now,
                       verified_by=None, version_ref=None, score=1.0, sensitivity="internal")
