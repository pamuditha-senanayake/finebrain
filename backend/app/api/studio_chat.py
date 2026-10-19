# studio_chat.py: the Workflow Studio assistant on Claude (step 9e). Claude reads the open workflow as data and answers
# with tools that only draft: a change goes through the same server review as the forms and comes back as a card the
# person must Confirm; a story comes back as a draft to confirm. A refused draft goes back to Claude once to fix.
# Used by: studio_routes.py (POST studio/chat). Uses: studio_chat_tools.py, studio_chat_context.py, studio_review.py, llm.py.
import uuid

from app.api.ask import address_of
from app.api.studio_chat_context import SYSTEM, card_of, context_of
from app.api.studio_chat_tools import TOOLS
from app.api.studio_draft import StudioError
from app.api.studio_review import review
from app.api.studio_state import Studio
from app.pipeline.observe import count, log_event

# Config
MOST_ROUNDS = 3
MOST_HISTORY = 12
NO_CLAUDE = "The Studio assistant needs Claude, sir, and no key is set. You can still change any part from its form."


def empty_reply(answer: str) -> dict:
    return {"answer": answer, "bullets": [], "cards": [], "suggestions": [], "proposal": None, "focus": None, "workflowId": None, "story": None}


def messages_of(history: list[dict], last: str) -> list[dict]:
    """Earlier turns as alternating messages, starting with the person, then the new message with its context."""
    turns = []
    for turn in history[-MOST_HISTORY:]:
        if turns and turns[-1]["role"] == turn["role"]:
            turns[-1]["content"] += f"\n{turn['text']}"
        elif turns or turn["role"] == "user":
            turns.append({"role": turn["role"], "content": turn["text"]})
    if turns and turns[-1]["role"] == "user":
        turns.pop()  # the new message is the person's turn
    return [*turns, {"role": "user", "content": last}]


def story_proposal(lane, st, person_id: str, draft: dict) -> dict:
    """The confirmed draft as a change: a new workflow, or its new cases added to this one."""
    if not draft.get("workflowId"):
        change = {"intent": "create", "kind": "workflow", "targetId": None, "workflowId": None,
                  "patch": {"name": draft["name"], "description": draft["story"]["problem"], "story": draft["story"]}}
    else:
        flow = st.flows[draft["workflowId"]]
        known = {s["id"] for s in (flow.get("story") or {}).get("scenarios", [])}
        story = {**draft["story"], "scenarios": [*(flow.get("story") or {}).get("scenarios", []), *(s for s in draft["story"]["scenarios"] if s["id"] not in known)]}
        change = {"intent": "update", "kind": "workflow", "targetId": flow["id"], "workflowId": flow["id"], "patch": {"story": story}}
    return review(lane, person_id, change, st)


def run_tool(lane, st, person_id: str, req: dict, name: str, args: dict, out: dict) -> str:
    """Do one tool call into `out` and say what happened, for Claude's next round."""
    if name == "propose_change":
        out["proposal"] = review(lane, person_id, {**args, "patch": args.get("patch") or {}}, st)
        rv = out["proposal"]["review"]
        out["focus"] = {"kind": args["kind"], "id": args["targetId"]} if args.get("targetId") else out["focus"]
        return f"Reviewed: {rv['verdict']}, C{rv['criticality']}, route {rv['authority']['route']} ({rv['authority']['approver']}). {rv['summary']}"
    if name == "draft_story":
        scenarios = [{**s, "id": f"sc-{uuid.uuid4().hex[:6]}", "coveredBy": []} for s in args["scenarios"]]
        out["story"] = {"workflowId": args.get("workflowId"), "name": args["name"], "story": {"problem": args["problem"], "today": args["today"], "scenarios": scenarios}}
        return f"Drafted {len(scenarios)} cases. The person will confirm or change them."
    if name == "confirm_story":
        if not req.get("story"):
            raise StudioError("There is no drafted story to confirm.", 422)
        out["proposal"] = story_proposal(lane, st, person_id, req["story"])
        return f"Proposal ready: {out['proposal']['title']}."
    if name == "show_items":
        out["cards"] = [card for card in (card_of(st, item_id) for item_id in args["ids"]) if card]
        return f"Showing {len(out['cards'])} cards."
    if name == "switch_workflow":
        if args["workflowId"] not in st.flows:
            raise StudioError("No workflow has that id.", 404)
        out["workflowId"] = args["workflowId"]
        return f"Opened {st.flows[args['workflowId']]['name']}."
    if name == "reply":
        out.update(answer=args["answer"], bullets=args.get("bullets", []), suggestions=[{"label": s, "prompt": s, "tone": "neutral"} for s in args.get("suggestions", [])])
        return "Sent."
    raise StudioError(f"Unknown tool {name}.", 400)


def chat(lane, chatter, person_id: str, req: dict) -> dict:
    """One assistant turn: Claude may draft, show and switch, then replies. Nothing is applied here."""
    people = lane.seed["people"]
    if person_id not in people:
        raise StudioError("Unknown person", 401)
    if chatter is None:
        return empty_reply(NO_CLAUDE)
    st = Studio.of(lane)
    flow = st.flows.get(req.get("workflowId")) or next(iter(st.flows.values()), None)
    if flow is None:
        return empty_reply("There are no workflows yet, sir. Describe a problem and I will draft one.")
    system = SYSTEM.format(address=address_of(people[person_id]))
    messages = messages_of(req.get("history") or [], f"{context_of(lane, st, flow, person_id, req.get('focus'), req.get('story'))}\n<message>\n{req['message']}\n</message>")
    out, reply = {**empty_reply(""), "answer": None}, None
    for _ in range(MOST_ROUNDS):
        reply = chatter(system, messages, TOOLS)
        uses = [block for block in reply.content if getattr(block, "type", "") == "tool_use"]
        if not uses:
            break
        results = []
        for block in uses:
            try:
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": run_tool(lane, st, person_id, req, block.name, block.input, out)})
            except StudioError as error:  # a refused draft goes back to Claude to fix
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(error), "is_error": True})
        if out["answer"] is not None:
            break
        messages += [{"role": "assistant", "content": [block.model_dump() for block in reply.content]}, {"role": "user", "content": results}]
    text = next((b.text for b in (reply.content if reply else []) if getattr(b, "type", "") == "text"), "").strip()
    count("studio.chat")
    log_event("STUDIO", "chat", workflow_id=flow["id"], proposal=bool(out["proposal"]), story=bool(out["story"]))
    return {**out, "answer": out["answer"] or text or "I could not finish that answer, sir. Please ask again."}
