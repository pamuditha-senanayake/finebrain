# studio_draft.py: what a proposed Studio change would make, without touching the graph: the target before and after,
# and the field by field diff shown to the person. A port of materialize and diff in the mock engine; the browser only
# sends the intent and the patch, never the impact. Used by: studio_review.py, studio_apply.py. Uses: studio_spec.py, studio_state.py.
import copy
import re
import uuid

from app.api.studio_spec import FIELDS, KIND_LABEL, TOOL_LEVEL_LABEL, format_value, is_ref, label

# Config
SELECT_DEFAULTS = {"autonomy": "trainee", "accessLevel": "internal", "criticality": "3", "sensorKind": "inbox", "health": "ok", "level": "prebuilt",
                   "sensitivity": "internal", "sideEffect": "read"}
NUMBER_DEFAULTS = {"rateLimitPerMin": 60, "maxConcurrent": 2, "retentionDays": 365}


class StudioError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:32] or "item"


def default_fields(kind: str) -> dict:
    fields = {}
    for key, _, field_type, _, _, _ in FIELDS[kind]:
        fields[key] = ([] if field_type in ("refs", "list") else key == "enabled" if field_type == "boolean" else NUMBER_DEFAULTS.get(key, 0) if field_type == "number"
                       else SELECT_DEFAULTS.get(key, "") if field_type == "select" else "")
    return fields | ({"timezone": "Asia/Colombo"} if kind == "scheduler" else {}) | ({"model": "claude-sonnet-5-5"} if kind == "agent" else {})


def materialize(st, tenant: dict, person_id: str, change: dict) -> tuple[dict | None, dict | None, dict | None]:
    """(before, after, workflow). After is None for a delete; before is None for a create."""
    intent, kind, patch = change["intent"], change["kind"], change.get("patch") or {}
    if kind == "workflow":
        before = None if intent == "create" else st.flows.get(change.get("targetId"))
        if intent != "create" and not before:
            raise StudioError("Workflow not found", 404)
        if intent == "delete":
            return before, None, before
        base = copy.deepcopy(before) if before else {
            "id": f"wf_{slug(patch.get('name', 'new workflow')).replace('-', '_')}", "tenantId": tenant["tenant_id"], "name": patch.get("name", "New workflow"), "description": "",
            "topics": [], "status": "draft", "version": 0, "clusterId": tenant["cluster_id"], "dri": person_id, "editors": [], "criticality": 2, "members": [], "story": None,
            "updatedAt": "", "updatedBy": person_id}
        after = {**base, **{key: patch[key] for key in ("name", "description", "topics", "status", "dri", "story") if patch.get(key) is not None}}
        if (patch.get("fields") or {}).get("criticality") is not None:
            after["criticality"] = max(0, min(4, int(patch["fields"]["criticality"])))
        return before, after, before or after
    before = None if intent == "create" else st.items.get(change.get("targetId"))
    if intent != "create" and not before:
        raise StudioError(f"{KIND_LABEL[kind]} not found", 404)
    flow = None if kind == "tool" else st.flows.get((before or {}).get("workflowId") or change.get("workflowId"))
    if kind != "tool" and not flow:
        raise StudioError("Pick a workflow first", 400)
    if intent == "delete":
        return before, None, flow
    name = patch.get("name") or (before or {}).get("name") or f"New {KIND_LABEL[kind].lower()}"
    item_id = f"tool:{slug(name).replace('-', '.')}" if kind == "tool" else f"{flow['id'].removeprefix('wf_')}.{kind}.{slug(name)}-{uuid.uuid4().hex[:4]}"
    base = copy.deepcopy(before) if before else {"id": item_id, "kind": kind, "workflowId": None if kind == "tool" else flow["id"], "name": name, "description": "", "topics": [],
                                                 "status": "active", "version": 0, "dri": (flow or {}).get("dri", person_id), "fields": default_fields(kind), "updatedAt": "", "updatedBy": person_id}
    after = {**base, **{key: patch[key] for key in ("name", "description", "topics", "status", "dri") if patch.get(key) is not None},
             "fields": {**base["fields"], **(patch.get("fields") or {})}}
    return before, after, flow


def snapshot(target: dict) -> dict:
    fields = {"criticality": str(target["criticality"]), "dri": target["dri"]} if "members" in target else copy.deepcopy(target["fields"])
    return {"name": target["name"], "description": target["description"], "topics": list(target["topics"]), "status": target["status"], "fields": fields}


def shown(st, kind: str, key: str, value) -> str | None:
    if value is None or value == "" or value == []:
        return None
    if kind != "workflow" and is_ref(kind, key):
        return ", ".join(st.name_of(ref_id) for ref_id in (value if isinstance(value, list) else [str(value)]))
    if kind == "tool" and key == "level":
        return TOOL_LEVEL_LABEL.get(str(value), str(value))
    if kind == "tool" and key == "code":
        return f"{len(str(value).strip().splitlines())} lines"
    return format_value(value, key)


def diff(st, kind: str, before: dict | None, after: dict | None) -> list[dict]:
    if before and not after:
        return [{"field": "_delete", "label": KIND_LABEL[kind], "before": before["name"], "after": "deleted"}]
    b, a = (snapshot(before) if before else None), (snapshot(after) if after else None)
    changes = []
    for key in ("name", "description", "topics", "status"):
        if (b or {}).get(key) != (a or {}).get(key):
            changes.append({"field": key, "label": label(kind, key), "before": shown(st, kind, key, (b or {}).get(key)), "after": shown(st, kind, key, (a or {}).get(key))})
    for key in dict.fromkeys([*((b or {}).get("fields") or {}), *((a or {}).get("fields") or {})]):
        was, now = ((b or {}).get("fields") or {}).get(key), ((a or {}).get("fields") or {}).get(key)
        if was != now:
            changes.append({"field": key, "label": label(kind, key), "before": shown(st, kind, key, was), "after": shown(st, kind, key, now)})
    if before and after and before.get("dri") != after.get("dri") and "members" not in before:
        changes.append({"field": "dri", "label": "DRI", "before": before["dri"], "after": after["dri"]})
    if kind == "workflow" and after:
        story_before, story_after = (before or {}).get("story"), after.get("story")
        if story_after and (story_before or {}).get("problem") != story_after["problem"]:
            changes.append({"field": "story.problem", "label": "Problem", "before": (story_before or {}).get("problem"), "after": story_after["problem"]})
        if (story_before or {}).get("scenarios", []) != (story_after or {}).get("scenarios", []):
            count = lambda s: f"{len(s['scenarios'])} scenario{'' if len(s['scenarios']) == 1 else 's'}" if s else None  # noqa: E731
            changes.append({"field": "story.scenarios", "label": "Scenarios", "before": count(story_before), "after": count(story_after)})
    return [c for c in changes if c["before"] != c["after"]]
