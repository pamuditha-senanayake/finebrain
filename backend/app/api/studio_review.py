# studio_review.py: the Edit Review Agent on the server. From a proposed change (intent, kind, target, patch) it
# rebuilds the proposal: the diff, what it breaks or changes, who else is hit through shared tools, a verdict, a
# criticality with reasons, and who may confirm it. A port of review() in the mock engine; nothing the browser claims
# about impact is used. Used by: routes (studio/review), studio_apply.py. Uses: studio_draft.py, studio_findings.py, studio_rules.py.
from app.api.studio_draft import StudioError, diff, materialize
from app.api.studio_findings import Studio, fix, item_findings, unique_by_label, without
from app.api.studio_rules import authority, level_for, touches
from app.api.studio_spec import KIND_LABEL, refs_of, spec

# Config
REVIEWER = "Edit Review Agent"
WORDING = {"name", "description", "topics"}


def review(lane, person_id: str, change: dict, st: Studio | None = None) -> dict:
    st = st or Studio.of(lane)
    before, after, flow = materialize(st, lane.seed, person_id, change)
    changes = diff(st, change["kind"], before, after)
    if change["intent"] == "update" and not changes:
        raise StudioError("Nothing would change. Say what the new value should be.", 422)
    target = after or before
    findings, fixes, affected, others = [], [], [], []

    def touch(it: dict, how: str) -> None:
        if all(a["id"] != it["id"] for a in affected):
            is_flow = "members" in it
            affected.append({"kind": "workflow" if is_flow else it["kind"], "id": it["id"], "name": it["name"], "workflowId": it["id"] if is_flow else it["workflowId"], "how": how})

    touch(target, {"create": "created", "delete": "deleted"}.get(change["intent"], "changed"))
    if change["kind"] == "workflow":
        members = st.members(target)
        if change["intent"] == "delete" and members:
            findings.append({"severity": "break", "text": f"Deleting {target['name']} removes its {len(members)} members. Shared tools stay.", "ref": None})
        if after and before and after["status"] != "active" and before["status"] == "active":
            findings.append({"severity": "warn", "text": f"Every skill in {target['name']} stops taking work while it is {after['status']}.", "ref": None})
        for m in members[:12] if change["intent"] == "delete" or any(c["field"] == "status" for c in changes) else []:
            touch(m, "deleted with the workflow" if change["intent"] == "delete" else "stops with the workflow")
    else:
        item_checks(st, change, before, target, flow, changes, findings, fixes, others, touch)
    if change["intent"] == "update" and all(c["field"] in WORDING for c in changes):
        del affected[1:]
    verdict = "breaking" if any(f["severity"] == "break" for f in findings) else "moderate" if any(f["severity"] == "warn" for f in findings) or change["intent"] != "update" else "minimal"
    clusters = {c for c in [(flow or {}).get("clusterId"), *(st.flows.get(o["id"], {}).get("clusterId") for o in others)] if c}
    level, reasons = level_for(change, [c["field"] for c in changes], before, after, verdict, touches(st, change["kind"], target, [c["field"] for c in changes]), len(clusters))
    people = lane.seed["people"]
    if person_id not in people:
        raise StudioError("Unknown person", 401)
    return {"input": change, "title": f"{ {'create': 'Create', 'delete': 'Delete'}.get(change['intent'], 'Update') } {KIND_LABEL[change['kind']].lower()}: {target['name']}",
            "targetName": target["name"], "changes": changes,
            "review": {"reviewer": REVIEWER, "verdict": verdict, "criticality": level, "criticalityReasons": reasons, "summary": summary(verdict, findings, fixes, affected, flow),
                       "findings": findings, "affected": affected, "otherWorkflows": others, "fixes": unique_by_label(fixes)[:4],
                       "authority": authority(person_id, people[person_id], flow, level, verdict)}}


def item_checks(st, change, before, item, flow, changes, findings, fixes, others, touch) -> None:
    inbound = st.referrers(item["id"], flow)
    for r in inbound:
        touch(r["item"], f"{r['rel']} {item['name']}")
    for r in refs_of(item["kind"], item["fields"]):
        if r["id"] in st.items:
            touch(st.items[r["id"]], f"{item['name']} {r['rel']} it")
    if item["kind"] == "tool":
        others += [{"id": w["id"], "name": w["name"], "via": f"uses {item['name']}"} for w in st.using_tool(item["id"]) if w["id"] != (flow or {}).get("id")]
    if change["intent"] == "delete":
        for r in inbound:
            findings.append({"severity": "info" if r["item"]["status"] == "retired" else "break", "text": f"{r['item']['name']} {r['rel']} {item['name']}. After the delete it points at nothing.",
                             "ref": {"kind": r["item"]["kind"], "id": r["item"]["id"]}})
            fixes.append(fix(f"Remove {item['name']} from {r['item']['name']} first", without(r["item"], r["key"], item["id"])))
        if not inbound:
            findings.append({"severity": "info", "text": f"Nothing else in the workflow points at {item['name']}.", "ref": None})
        return
    scope = [item if x["id"] == item["id"] else x for x in st.scope(flow)] if flow else [item]
    if change["intent"] == "create" and flow and item["kind"] != "tool":
        scope.append(item)
    own, own_fixes = item_findings(st, item, scope)
    known = {f["text"] for f in item_findings(st, before, st.scope(flow) if flow else [before])[0]} if before else set()
    findings += [{**f, "severity": "info", "text": f"Already true before this change: {f['text']}"} if f["text"] in known else f for f in own]
    fixes += own_fixes
    for r in inbound:  # what depends on this item may break because of it, here or, for a shared tool, elsewhere
        home = st.flows.get(r["item"]["workflowId"])
        was = st.scope(home) if home else [r["item"]]
        old = {f["text"] for f in item_findings(st, r["item"], was)[0]}
        for f in item_findings(st, r["item"], [item if x["id"] == item["id"] else x for x in was])[0]:
            if f["severity"] == "break" and f["text"] not in old and all(g["text"] != f["text"] for g in findings):
                findings.append(f)
    field_checks(st, before, item, inbound, changes, findings)
    if item["kind"] == "tool" and others and change["intent"] == "update":
        findings.append({"severity": "warn", "text": f"{item['name']} is shared. {len(others)} other workflow{'s' if len(others) > 1 else ''} change with it: {', '.join(o['name'] for o in others)}.", "ref": None})
    if change["intent"] == "create":
        findings.append({"severity": "info", "text": f"{item['name']} is added to {(flow or {}).get('name', 'the shared tool library')}.", "ref": None})
    if all(c["field"] in WORDING for c in changes):
        findings.append({"severity": "info", "text": "Only wording and topics change. Agents keep behaving the same way.", "ref": None})


def field_checks(st, before, item, inbound, changes, findings) -> None:
    say = lambda severity, text, ref=None: findings.append({"severity": severity, "text": text, "ref": ref})  # noqa: E731
    if before and item["status"] != "active" and before["status"] == "active":
        for r in inbound:
            if r["item"]["status"] == "active":
                say("break" if item["kind"] in ("tool", "agent") else "warn", f"{r['item']['name']} {r['rel']} {item['name']}, which becomes {item['status']}.", {"kind": r["item"]["kind"], "id": r["item"]["id"]})
    params_moved = False
    for c in changes:
        if item["kind"] == "policy" and c["field"].startswith("param.") and before:
            was, now = before["fields"].get(c["field"]), item["fields"].get(c["field"])
            if isinstance(was, (int, float)) and isinstance(now, (int, float)) and was != now:
                params_moved = True
                say("warn", f"{c['label']} goes from {c['before']} to {c['after']}. " + ("More cases are handled without a person." if now > was else "More cases will escalate to people."))
        row = spec(item["kind"], c["field"])
        if row and row[2] in ("refs", "ref") and before:
            ids = lambda v: v if isinstance(v, list) else [v] if isinstance(v, str) and v else []  # noqa: E731
            was, now = ids(before["fields"].get(c["field"])), ids(item["fields"].get(c["field"]))
            for gone in [x for x in was if x not in now]:
                text = {"policy": f"{item['name']} will no longer be governed by {st.name_of(gone)}. Check that another policy still limits it.",
                        "agent": f"{st.name_of(gone)} stops {'receiving events from' if row[0] == 'feeds' else 'running'} {item['name']}.",
                        "sensor": f"{item['name']} stops reading {st.name_of(gone)}."}.get(row[3])
                if text:
                    say("info" if row[3] == "sensor" else "warn", text, {"kind": row[3], "id": gone})
            for added in [st.items[x] for x in now if x not in was and x in st.items]:
                if row[3] == "tool" and added["fields"].get("sideEffect") in ("money", "public"):
                    say("warn", f"{item['name']} gains {added['name']}, which {'moves money' if added['fields']['sideEffect'] == 'money' else 'publishes in public'}.", {"kind": "tool", "id": added["id"]})
        if item["kind"] == "policy" and c["field"] == "statement":
            say("warn", "The statement is what agents read. Skills governed by it will reason from the new wording.")
        if item["kind"] == "agent" and c["field"] == "autonomy":
            say("warn" if c["after"] == "autonomous" else "info", f"{item['name']} will act without supervision." if c["after"] == "autonomous" else f"{item['name']} will have more of its work checked by people.")
        if item["kind"] == "tool" and c["field"] == "sideEffect" and c["after"] in ("money", "public") and before:
            say("break", f"{item['name']} would start {'moving money' if c['after'] == 'money' else 'publishing in public'}. Every skill that uses it needs a fresh review.")
        if item["kind"] == "tool" and c["field"] == "capability" and before:
            say("break", f"Agents holding the old capability lose access to {item['name']} until they are granted the new one.")
    if params_moved and not any(c["field"] == "statement" for c in changes):
        say("warn", "The limits change but the statement does not. Agents read the statement, so update its wording too.")


def summary(verdict: str, findings: list, fixes: list, affected: list, flow: dict | None) -> str:
    breaks, warns = sum(f["severity"] == "break" for f in findings), sum(f["severity"] == "warn" for f in findings)
    if verdict == "breaking":
        return f"Breaking: {breaks} problem{'s' if breaks > 1 else ''} would stop part of {(flow or {}).get('name', 'the workflow')} from working." + (" Apply the fixes first, or send it for approval with them noted." if fixes else "")
    if verdict == "moderate":
        return f"Moderate: the workflow keeps working, but behaviour changes{f' in {warns} place' + ('s' if warns > 1 else '') if warns else ''}. Affects {len(affected) - 1} other item{'' if len(affected) == 2 else 's'}."
    return "Minimal: nothing else in the workflow changes behaviour."
