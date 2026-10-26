# studio_state.py: Workflow Studio's items and workflows in memory, with the lookups the review and the views need:
# a workflow's members and scope, who uses a shared tool, what points at an item, and the connections a sensor can listen to.
# Used by: studio_findings.py, studio_review.py, studio_views.py. Uses: studio_model.py, studio_spec.py, studio_activity.py.
from app.api import studio_activity, studio_model
from app.api.studio_spec import refs_of


class Studio:
    """Items and workflows as Studio sees them, with the lookups the review needs."""

    def __init__(self, items: list[dict], flows: list[dict], sources: dict[str, dict] | None = None):
        self.items = {item["id"]: item for item in items}
        self.flows = {flow["id"]: flow for flow in flows}
        self.sources = sources or {}  # connection id to its name and status, for sensors

    @classmethod
    def of(cls, lane) -> "Studio":
        return cls(studio_model.items(lane), studio_model.workflows(lane), studio_activity.message_sources(lane))

    def members(self, flow: dict) -> list[dict]:
        order = studio_model.MEMBER_KINDS
        mine = [self.items[m] for m in flow["members"] if m in self.items]
        return sorted(mine, key=lambda i: (order.index(i["kind"]), i["name"]))

    def tool_ids(self, flow: dict) -> list[str]:
        return list(dict.fromkeys(r["id"] for m in self.members(flow) for r in refs_of(m["kind"], m["fields"]) if r["ref"] == "tool"))

    def scope(self, flow: dict) -> list[dict]:
        return self.members(flow) + [self.items[t] for t in self.tool_ids(flow) if t in self.items]

    def using_tool(self, tool_id: str) -> list[dict]:
        return [flow for flow in self.flows.values() if tool_id in self.tool_ids(flow)]

    def referrers(self, item_id: str, flow: dict | None) -> list[dict]:
        pool = self.members(flow) if flow and not item_id.startswith("tool:") else self.items.values()
        return [{"item": it, "rel": r["rel"], "key": r["key"]} for it in pool for r in refs_of(it["kind"], it["fields"]) if r["id"] == item_id]

    def name_of(self, item_id: str) -> str:
        return (self.items.get(item_id) or self.flows.get(item_id) or {}).get("name", item_id)
