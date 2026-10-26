# studio_findings.py: the Edit Review Agent's checks on one item, and the workflow health check built from them.
# A port of itemFindings in frontend/lib/mock/studio/engine.ts, plus one real check the mock lacked: a skill may only
# use tools that have a runner in S9. Used by: studio_review.py, studio_views.py. Uses: studio_state.py, studio_spec.py, tools.py.
import re

from typing import get_args

from app.api.studio_spec import refs_of, valid_cron
from app.api.studio_state import Studio
from app.pipeline.contracts_signal import SourceType
from app.pipeline.stages_govern import CAPABILITY_FOR_ACTION
from app.pipeline.stages_retrieve import READ_CAPABILITY
from app.pipeline.tool_runners import RUNNERS
from app.pipeline.tools import TOOLS

# Config
TOOL_TAG = re.compile(r"\s*\[.*\]$")
CHANNELS = set(get_args(SourceType))  # a sensor of a seeded workflow names its channel; keyword rules route those
CHECKED = {READ_CAPABILITY, *CAPABILITY_FOR_ACTION.values()}  # the capabilities S5 and S7 check


def fix(label: str, change: dict) -> dict:
    return {"label": label, "prompt": label, "tone": "fix", "input": change}


def edit_list(item: dict, key: str, values: list) -> dict:
    return {"intent": "update", "kind": item["kind"], "targetId": item["id"], "workflowId": item["workflowId"], "patch": {"fields": {key: values}}}


def without(item: dict, key: str, ref_id: str) -> dict:
    value = item["fields"].get(key)
    return edit_list(item, key, [x for x in value if x != ref_id]) if isinstance(value, list) else {**edit_list(item, key, []), "patch": {"fields": {key: ""}}}


def adding(item: dict, key: str, value: str) -> dict:
    return edit_list(item, key, list(dict.fromkeys([*(item["fields"].get(key) or []), value])))


def sandbox_test(code: str) -> str | None:
    """Why a custom tool fails its test run, or None. A real sandbox runs the code; this checks the same contract."""
    if not code.strip():
        return "there is no code yet."
    if not re.search(r"export\s+async\s+function\s+run\s*\(", code):
        return "it needs an exported async run(input) function."
    if reach := re.search(r"process\.env|child_process|require\(|\beval\(|new Function", code):
        return f"it reaches outside the sandbox ({reach.group(0)})."
    return None if code.count("{") == code.count("}") else "its braces do not balance."


def item_findings(st: Studio, it: dict, scope: list[dict]) -> tuple[list[dict], list[dict]]:
    """Problems in the state an item would be in, and fixes for them."""
    findings, fixes, here, ref, f = [], [], {x["id"]: x for x in scope}, {"kind": it["kind"], "id": it["id"]}, it["fields"]
    say = lambda severity, text, where=ref: findings.append({"severity": severity, "text": text, "ref": where})  # noqa: E731
    if it["status"] == "retired":
        return findings, fixes
    for r in refs_of(it["kind"], f):
        target = here.get(r["id"]) or st.items.get(r["id"])
        if not target:
            say("break", f"{it['name']} {r['rel']} an item that no longer exists ({r['id']}).")
            fixes.append(fix(f"Remove the missing link from {it['name']}", without(it, r["key"], r["id"])))
        elif r["ref"] != "tool" and target["workflowId"] != it["workflowId"]:
            say("break", f"{it['name']} {r['rel']} {target['name']}, which belongs to another workflow. Only tools are shared.")
            fixes.append(fix(f"Remove {target['name']} from {it['name']}", without(it, r["key"], r["id"])))
        elif target["status"] in ("retired", "paused"):
            say("break" if r["ref"] in ("tool", "agent") else "warn", f"{it['name']} {r['rel']} {target['name']}, which is {target['status']}.")
            fixes.append(fix(f"Resume {target['name']}", {"intent": "update", "kind": target["kind"], "targetId": target["id"], "workflowId": target["workflowId"], "patch": {"status": "active"}}))
    if it["kind"] == "skill":
        agents = [here[a] for a in f.get("agents", []) if a in here and here[a]["status"] == "active"]
        if not agents and it["status"] == "active":
            say("break", f"No active agent runs {it['name']}, so it will never execute.")
            if candidate := next((x for x in scope if x["kind"] == "agent" and x["status"] == "active"), None):
                fixes.append(fix(f"Assign {candidate['name']} to {it['name']}", adding(it, "agents", candidate["id"])))
        tools = f.get("tools", [])
        if not tools and it["status"] == "active":
            say("break", f"{it['name']} lists no tools, so its agent can never act: S4 refuses to start it. Add reply customer and escalate at least.")
            fixes.append(fix(f"Give {it['name']} reply customer and escalate", edit_list(it, "tools", ["tool:reply_customer", "tool:escalate"])))
        for step in f.get("steps", []):
            if (m := re.search(r"\[(tool:[^\]]+)\]", step)) and m.group(1) not in tools:
                shown = TOOL_TAG.sub("", step)
                say("break", f"Step \"{shown}\" calls {m.group(1).removeprefix('tool:')}, but {it['name']} does not list that tool.")
                fixes.append(fix(f"Add {m.group(1).removeprefix('tool:')} to {it['name']}", adding(it, "tools", m.group(1))))
        for tool_id in tools:
            tool = st.items.get(tool_id)
            if tool and tool["fields"].get("level") != "custom" and tool_id.removeprefix("tool:") not in TOOLS:
                say("break", f"{tool['name']} has no runner yet, so agents cannot call it from {it['name']}.")
            capability = str((tool or {}).get("fields", {}).get("capability") or "")
            for agent in agents if capability else []:
                if capability not in agent["fields"].get("capabilities", []):
                    say("break", f"{agent['name']} runs {it['name']} but lacks {capability}, which {tool['name']} needs. Calls will be denied.", {"kind": "agent", "id": agent["id"]})
                    fixes.append(fix(f"Grant {capability} to {agent['name']}", adding(agent, "capabilities", capability)))
        if not f.get("policies"):
            say("warn", f"{it['name']} has no governing policy. Nothing limits what it may do.")
        if int(f.get("evalCases") or 0) < 10:
            say("warn", f"{it['name']} has {int(f.get('evalCases') or 0)} eval cases. Ten or more make a change safe to judge.")
    more_findings(st, it, scope, say)
    return findings, fixes


def more_findings(st: Studio, it: dict, scope: list[dict], say) -> None:
    """The checks for schedulers, sensors, agents, templates, custom tools and policies."""
    f, kind, active = it["fields"], it["kind"], it["status"] == "active"
    if kind == "scheduler":
        if not valid_cron(str(f.get("cron", ""))):
            say("break", f"{it['name']} has an invalid cron \"{f.get('cron', '')}\". It will never fire.")
        if not f.get("target"):
            say("break", f"{it['name']} does not say which skill to run.")
        if f.get("enabled") is False:
            say("warn", f"{it['name']} is turned off. {st.name_of(str(f.get('target')))} will not run on schedule.")
    source = str(f.get("source") or "")
    if kind == "sensor" and active and source not in st.sources and source not in CHANNELS:
        known = ", ".join(f"{s['name']} ({s['id']})" for s in st.sources.values()) or "none yet; create one in Connections first"
        say("break", f"{it['name']} listens to \"{source or 'nothing'}\", which is not a connection, so no message reaches this workflow. Connections: {known}.")
    if kind == "sensor" and f.get("health") in ("down", "degraded"):
        say("warn" if f["health"] == "down" else "info", f"{it['name']} is {f['health']}." + (" Skills reading it work on stale data." if f["health"] == "down" else ""))
    if kind == "agent" and active and not any(x["kind"] == "skill" and x["status"] == "active" and it["id"] in x["fields"].get("agents", []) for x in scope):
        say("warn", f"{it['name']} runs no skill in this workflow.")
    if kind == "template" and active and not any((x["kind"] == "skill" and it["id"] in x["fields"].get("templates", [])) or (x["kind"] == "loop" and x["fields"].get("learning") == it["id"]) for x in scope):
        say("warn", f"No skill fills {it['name']}, so it will go stale.")
    if kind == "tool" and active and f.get("level") != "custom" and str(f.get("endpoint") or "") not in RUNNERS:
        say("break", f"{it['name']} goes to \"{f.get('endpoint') or 'nothing'}\", which S9 does not serve, so every call fails. Endpoints: {', '.join(RUNNERS)}.")
    if kind == "tool" and f.get("capability") and f["capability"] not in CHECKED:
        say("warn", f"{it['name']} needs \"{f['capability']}\", which no check uses. Pick one of: {', '.join(sorted(CHECKED))}.")
    for capability in (f.get("capabilities") or []) if kind == "agent" and active else []:
        if capability not in CHECKED:
            say("break", f"{it['name']} holds \"{capability}\", which no check uses, so it allows nothing. Pick from: {', '.join(sorted(CHECKED))}.")
    if kind == "tool" and f.get("level") == "custom":
        failed = sandbox_test(str(f.get("code", "")))
        say("break" if failed else "info", f"{it['name']} failed its sandbox test run: {failed}" if failed else f"{it['name']} passed its sandbox test run.")
    if kind == "policy" and active and not any((x["kind"] == "skill" and it["id"] in x["fields"].get("policies", [])) or (x["kind"] == "loop" and it["id"] in x["fields"].get("guards", [])) for x in scope):
        say("info", f"{it['name']} does not govern any skill yet.")


def health(st: Studio, flow: dict) -> dict:
    """Every problem in a workflow, its shared tools included, with one fix per label."""
    findings, fixes, scope = [], [], st.scope(flow)
    for it in scope:
        found, fixed = item_findings(st, it, scope)
        findings += found
        fixes += fixed
    return {"findings": findings + activity_findings(flow, scope), "fixes": unique_by_label(fixes)}


def activity_findings(flow: dict, scope: list[dict]) -> list[dict]:
    """A workflow is one activity: one skill holds every case's steps, and a sensor must feed it."""
    skills = [x for x in scope if x["kind"] == "skill" and x["status"] == "active"]
    ref = {"kind": "workflow", "id": flow["id"]}
    found = [{"severity": "warn", "ref": ref, "text": f"{flow['name']} has {len(skills)} skills, but an activity runs one: {skills[0]['name']}. Put every case's steps there."}] if len(skills) > 1 else []
    if not any(x["kind"] == "sensor" for x in scope):
        found.append({"severity": "info", "ref": ref, "text": f"No sensor feeds {flow['name']} yet, so no message reaches it."})
    return found


def unique_by_label(fixes: list[dict]) -> list[dict]:
    seen, kept = set(), []
    for item in fixes:
        if item["label"] not in seen:
            seen.add(item["label"])
            kept.append(item)
    return kept
