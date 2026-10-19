# studio_chat_tools.py: the tools the Studio assistant (Claude) may call. None of them writes: propose_change only
# drafts a change for the server review and the person's Confirm; draft_story and confirm_story shape the problem and its
# cases; show_items
# and switch_workflow steer the screen; reply carries the answer. Used by: studio_chat.py. Uses: nothing local.

# Config
KINDS = ["workflow", "skill", "agent", "policy", "template", "sensor", "scheduler", "loop", "tool"]
STATUSES = ["active", "draft", "paused", "retired"]
MOST_SCENARIOS = 6

PROPOSE = {
    "name": "propose_change",
    "description": "Draft one change for the person to review and confirm. The server reviews it and shows a card; nothing changes until they press Confirm. "
                   "For update and delete give targetId. For a new member give workflowId; tools are shared and take workflowId null. "
                   "In patch.fields give only the fields that change, using the field names listed in the context; list fields take the whole new list.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["intent", "kind", "targetId", "workflowId", "patch"], "properties": {
        "intent": {"type": "string", "enum": ["create", "update", "delete"]},
        "kind": {"type": "string", "enum": KINDS},
        "targetId": {"type": ["string", "null"]},
        "workflowId": {"type": ["string", "null"]},
        "patch": {"type": "object", "additionalProperties": False, "properties": {
            "name": {"type": "string"}, "description": {"type": "string"}, "topics": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": STATUSES}, "dri": {"type": "string"},
            "fields": {"type": "object", "description": "Field name to new value: text, number, true/false, or a list of text"},
        }},
    }},
}

STORY = {
    "name": "draft_story",
    "description": "Draft why a workflow exists: the problem, how it is handled today, and up to six concrete cases written as Given, When, Then today, and the goal. "
                   "The person confirms or edits it before anything changes. workflowId null starts a new workflow with this name.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["workflowId", "name", "problem", "today", "scenarios"], "properties": {
        "workflowId": {"type": ["string", "null"]}, "name": {"type": "string"}, "problem": {"type": "string"}, "today": {"type": "string"},
        "scenarios": {"type": "array", "maxItems": MOST_SCENARIOS, "items": {"type": "object", "additionalProperties": False, "required": ["title", "given", "when", "then", "goal"], "properties": {
            "title": {"type": "string"}, "given": {"type": "array", "items": {"type": "string"}}, "when": {"type": "string"},
            "then": {"type": "array", "items": {"type": "string"}, "description": "What happens today"}, "goal": {"type": "string", "description": "What should happen instead"}}}},
    }},
}

CONFIRM_STORY = {
    "name": "confirm_story",
    "description": "When the person agrees with the story you drafted (the draft is in the context), call this. The server turns that exact draft into a "
                   "proposal card: a new workflow, or new cases added to this one.",
    "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
}

SHOW = {
    "name": "show_items",
    "description": "Show up to four parts of the workflow as cards, by id, when it helps the person see what you mean.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["ids"], "properties": {"ids": {"type": "array", "maxItems": 4, "items": {"type": "string"}}}},
}

SWITCH = {
    "name": "switch_workflow",
    "description": "Open another workflow by id when the person asks about it.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["workflowId"], "properties": {"workflowId": {"type": "string"}}},
}

REPLY = {
    "name": "reply",
    "description": "Always call this last, once: your answer to the person. answer is one to three short sentences; bullets at most five short lines; "
                   "suggestions at most three next messages the person might send, each under eight words.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["answer"], "properties": {
        "answer": {"type": "string"}, "bullets": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
        "suggestions": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
    }},
}

TOOLS = [PROPOSE, STORY, CONFIRM_STORY, SHOW, SWITCH, REPLY]
