# hq2_history.py: the second half of Finebase HQ-2's stored history: runs for the A1 to A5 jobs, their approvals and decisions, the audit
# trail, the chats L3 shows, and some Ask the Brain history. Runs are scripted (no model call). Each writer checks first, so a second
# run adds nothing. Used by: seed_hq2.py. Uses: hq2_cast.py, hq2_world.py, the lane's records, audit and object store.
import json
from datetime import datetime, timedelta

from app.pipeline import conversation_log
from app.pipeline.contracts_reason import AccessDecision, ProposedAction
from app.pipeline.contracts_run import ActionResult, ApprovalRequest, Approvers, Cost, Decision, RunRecord, RunStep
from app.pipeline.contracts_signal import Signal, TaskRequest, VersionRef
from app.pipeline.contracts_start import ConversationMessage, ConversationState, OpenRun
from app.pipeline.stages_orchestrate_chat import MESSAGES_KIND, RUNS_KIND
from scripts.hq2_cast import CLIENTS, CLUSTER
from scripts.hq2_world import SKILLS

# Config
STEWARD = {"h-ruwan": "h-ruwan", "h-imashi": "h-imashi", "h-udayanga": "h-udayanga"}
AGENT_OF = {s[0]: (s[4], s[5]) for s in SKILLS}  # skill id: (agent, activity)
TOOL = {"reply_customer": ("tool_reply_email", 2), "escalate": ("tool_escalate", 1)}
NOW = datetime.fromisoformat("2026-10-28T18:00:00+05:30")
MEETING = {"lanka_print": "doc_meet_lanka_1013", "ocean_foods": "doc_meet_ocean_1015", "bluebird": "doc_meet_bluebird_1016", "kandy_tea": "doc_meet_kandy_1022", "harbor": "doc_meet_harbor_1020", "nila": "doc_meet_nila_1023"}
WEEKS = {0: "2026-10-26", 1: "2026-10-19", 2: "2026-10-12"}  # the Monday of each week, newest first


def at(day: str, hours: float) -> datetime:
    return datetime.fromisoformat(f"{day}T09:00:00+05:30") + timedelta(hours=hours)


def specs() -> list[dict]:
    """Every scripted run: A1 weekly updates (three weeks, six clients), A3 transcripts, A4 spend checks, A5 client questions."""
    rows, n = [], 0
    for w in (2, 1, 0):
        for c, (cid, name, project, platform, lead, *_ ) in enumerate(CLIENTS):
            if platform == "gmail" and w == 2 or (cid == "harbor" and w == 2) or (cid == "nila" and w == 2):
                continue  # these projects had not started
            outcome = "resolved" if w else ("awaiting_approval" if c % 3 == 0 else "resolved" if c % 3 == 1 else "escalated")
            if cid == "kandy_tea" and w == 1:
                outcome = "abandoned"  # the update that was never sent (19 Oct stand-up)
            rows.append({"skill": "skill_client_update", "client": cid, "text": f"Weekly update for {name}: {project}", "outcome": outcome, "when": at(WEEKS[w], c * 2 + 4),
                         "lead": lead, "cites": [f"{MEETING[cid]}_c1"], "channel": platform})
    for day, doc, text, outcome in (("2026-10-13", "doc_meet_lanka_1013", "Tasks from the Lanka Print meeting, 13 Oct", "resolved"), ("2026-10-15", "doc_meet_ocean_1015", "Tasks from the Ocean Foods meeting, 15 Oct", "resolved"),
                                    ("2026-10-16", "doc_meet_bluebird_1016", "Tasks from the Bluebird Clinics review, 16 Oct", "resolved"), ("2026-10-20", "doc_meet_harbor_1020", "Tasks from the Harbor kickoff, 20 Oct", "resolved"),
                                    ("2026-10-23", "doc_meet_nila_1023", "Tasks from the Nila sprint review, 23 Oct", "resolved"), ("2026-10-26", "doc_meet_internal_1026", "Tasks from the team stand-up, 26 Oct", "escalated")):
        rows.append({"skill": "skill_meeting_to_tasks", "client": None, "text": text, "outcome": outcome, "when": at(day, 8), "lead": "h-ruwan", "cites": [f"{doc}_c1", f"{doc}_c2"], "channel": "upload"})
    for day, doc, text, outcome in (("2026-09-02", "doc_blaze_aug", "Spend check: August Blaze bill", "resolved"), ("2026-10-02", "doc_blaze_sep", "Spend check: September Blaze bill", "resolved"),
                                    ("2026-10-27", "doc_blaze_oct", "Alert: October Blaze forecast is 40 percent over budget", "escalated"), ("2026-10-28", "doc_subs_oct", "Alert: Linear added without approval", "awaiting_approval")):
        rows.append({"skill": "skill_spend_check", "client": None, "text": text, "outcome": outcome, "when": at(day, 7), "lead": "h-pamuditha", "cites": [f"{doc}_c1", "policy_spend_v2_s3"], "channel": "poll"})
    for day, text, outcome, cites in (("2026-10-22", "Progress check: Booking form PR open for 9 days", "escalated", ["doc_github_week43_c2"]), ("2026-10-27", "Progress check: three tasks open since 19 Oct", "resolved", ["doc_slack_internal_1027_c1", "doc_meet_internal_1026_c1"]),
                                      ("2026-10-28", "Progress check: Sachini is blocked on Ocean Foods logo files", "resolved", ["doc_slack_internal_1027_c3"])):
        rows.append({"skill": "skill_member_progress", "client": None, "text": text, "outcome": outcome, "when": at(day, 6), "lead": "h-ruwan", "cites": cites, "channel": "webhook"})
    for day, text, outcome, cites in (("2026-10-22", "Grant draft: Open Research Fund is missing a school letter", "escalated", ["doc_grant_draft_c2", "doc_mail_grant_1012_c2"]), ("2026-10-18", "Deck draft: Cargo Hack 2026 outline checked", "resolved", ["doc_deck_hackathon_c1"]),
                                      ("2026-09-28", "Google Doc check: Harbor and Nila sections missing", "resolved", ["doc_what_we_build_c2"])):
        rows.append({"skill": "skill_grant_docs", "client": None, "text": text, "outcome": outcome, "when": at(day, 5), "lead": "h-imashi", "cites": cites, "channel": "upload"})
    for i, (cid, platform, when, text, outcome, cite) in enumerate(QUESTIONS):
        rows.append({"skill": "skill_client_questions", "client": cid, "text": text, "outcome": outcome, "when": when, "lead": next(c[4] for c in CLIENTS if c[0] == cid), "cites": cite, "channel": platform, "question": i})
    for i, row in enumerate(rows):
        row["run_id"] = f"run_hq2_{i:03d}"
    return rows


# (client, platform, when, subject, outcome, cited items). The chat text is in CHATS, by the same index.
QUESTIONS = [
    ("lanka_print", "slack", at("2026-10-22", 3), "Is the second payment due on the 24th or the 31st?", "resolved", ["doc_slack_lanka_1022_c2", "policy_payments_v1_s1"]),
    ("ocean_foods", "whatsapp", at("2026-10-21", 5), "Can we pay half now and half after launch?", "awaiting_approval", ["doc_wa_ocean_1022_c1", "policy_payments_v1_s1"]),
    ("kandy_tea", "whatsapp", at("2026-10-27", 4), "Is there a refund if the launch is late?", "resolved", ["policy_refund_v2_s1", "policy_refund_v2_s2"]),
    ("nila", "gmail", at("2026-10-26", 6), "Which first payment is correct, 2,150 or 2,300?", "awaiting_approval", ["doc_mail_nila_1005_c2", "doc_mail_nila_1026_c2"]),
    ("bluebird", "slack", at("2026-10-16", 6), "Does the fee cover a third branch in December?", "escalated", ["doc_meet_bluebird_1016_c3"]),
    ("harbor", "slack", at("2026-10-24", 2), "When do we see the signature screen?", "resolved", ["doc_slack_harbor_1024_c2", "doc_meet_harbor_1020_c1"]),
    ("kandy_tea", "whatsapp", at("2026-10-23", 4), "How much do I still owe?", "resolved", ["doc_wa_kandy_1023_c2", "doc_stripe_oct_c2"]),
    ("lanka_print", "slack", at("2026-10-22", 1), "Can we get the delivery report as a PDF before the 24th?", "resolved", ["doc_slack_lanka_1022_c2", "doc_meet_lanka_1013_c3"])]
CHATS = [
    ("Can you tell me, is the second payment due on the 24th or the 31st?", "The October invoice was issued on 16 October with 15 days to pay, so it is due on 31 October."),
    ("Can we pay half now and half after launch?", "We can accept half on 20 October and half on 6 November if you confirm in writing. A steward will confirm this with you."),
    ("Is there a refund if the launch is late?", "A refund is possible within 14 days of paying an invoice, and up to USD 500 is approved automatically."),
    ("The Stripe link says USD 2,150 but we expected USD 2,300. Which is correct?", "The first payment is 50 percent of USD 4,300, which is USD 2,150. The 2,300 figure had a setup fee that was removed on 8 October."),
    ("Does the monthly fee cover a third branch in December?", "I cannot find this in the agreement. A person from our team will answer you."),
    ("When do we see the signature screen on the driver app?", "The signature screen is planned for week 3 of phase 2, around 12 November."),
    ("How much do I still owe?", "The September invoice of USD 3,900 is unpaid. The October invoice is not issued yet."),
    ("Can we get the delivery report as a PDF before the 24th?", "The PDF report is with the project lead for review and will be sent before the 24th.")]
DENIES = [("run_hq2_deny_0", "agent_spend_watcher", "reply.draft", "chat:ocean_foods", "The spend watcher does not hold reply.draft", at("2026-10-27", 9)),
          ("run_hq2_deny_1", "agent_task_tracker", "refund.propose", "payment:pay_FB_20261007_0001", "The task tracker holds no refund capability", at("2026-10-26", 10))]


def action_of(spec: dict, kind: str) -> ProposedAction:
    tool, version = TOOL[kind]
    text = {"reply_customer": f"Draft: {spec['text']}", "escalate": f"Escalated: {spec['text']}"}[kind]
    return ProposedAction(run_id=spec["run_id"], step_id="step_act", action_type=kind, tool_id=tool, tool_version=version, arguments={"message_plain": text, "reason": text}, money=None,
                          touches={"money": False, "personal_data": spec["channel"] != "poll", "public_content": kind == "reply_customer", "legal_tax": False, "clusters": [CLUSTER]},
                          rationale_summary=f"Used {len(spec['cites'])} documents. {text}", citations=spec["cites"],
                          model={"provider": "scripted", "model_id": "recorded-demo", "input_tokens": 1800, "output_tokens": 240}, confidence=0.82)


def task_of(spec: dict) -> TaskRequest:
    agent, activity = AGENT_OF[spec["skill"]]
    return TaskRequest(task_id=spec["text"], signal_ids=[f"sig_{spec['run_id']}"], activity_id=activity, skill_ref=VersionRef(id=spec["skill"], version=1, branch="main", commit_id=f"cmt_hq2_{spec['skill']}"),
                       agent_id=agent, on_behalf_of=spec["lead"], resolver_rule_id=f"rr_{activity.removeprefix('act_')}", match_score=0.9, base_criticality=2, due_at=spec["when"] + timedelta(hours=4), priority=3)


def run_of(spec: dict, kind: str, needs_person: bool) -> RunRecord:
    agent, activity = AGENT_OF[spec["skill"]]
    start, outcome = spec["when"], spec["outcome"]
    step = lambda n, k, d, decision, reason, refs=(): RunStep(step_id=f"step_{n}", kind=k, started_at=start + timedelta(seconds=d), duration_ms=120 + d * 7, decision=decision, reason=reason, refs=list(refs), activity_id=activity)  # noqa: E731
    steps = [step(1, "retrieval", 0, "read", f"{len(spec['cites'])} items", spec["cites"]), step(2, "judgment", 4, "proposed", kind), step(3, "access_check", 5, "allow", "allow.capability")]
    if outcome == "awaiting_approval":
        steps.append(step(4, "human", 6, "approval_required", "client message needs a steward", [f"apr_{spec['run_id']}"]))
    elif outcome in ("resolved", "escalated"):
        steps.append(step(4, "tool", 9, "executed" if outcome == "resolved" else "escalated", kind))
    return RunRecord(run_id=spec["run_id"], task_id=spec["text"], agent_id=agent, skill_ref=VersionRef(id=spec["skill"], version=1, branch="main", commit_id=f"cmt_hq2_{spec['skill']}"), outcome=outcome,
                     steps=steps, template_fills=[], human_touch=needs_person or outcome == "escalated", cost=Cost(input_tokens=1800, output_tokens=240, usd_micro=9200), latency_ms=2400 + len(spec["text"]) * 11,
                     trace_object_uri=f"s3://brain/finebase-hq-2/traces/{spec['run_id']}.json", decided_by=spec["lead"] if outcome == "resolved" and needs_person else "auto by policy" if outcome == "resolved" else None)


def entry(lane, event_id: str, topic: str, payload, when: datetime, producer: str, corr: str) -> tuple:
    body = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    return (when, event_id, topic, {"payload": body, "occurred_at": when.isoformat(), "producer": producer, "correlation_id": corr})


def seed_runs(lane) -> int:
    """Runs, traces, approvals, decisions and the audit entries that belong to them. Returns the runs added."""
    added, audit_rows = 0, []
    for spec in specs():
        kind = "escalate" if spec["outcome"] == "escalated" or spec["skill"] in ("skill_spend_check", "skill_grant_docs") else "reply_customer"
        founder = spec["skill"] == "skill_spend_check" and spec["outcome"] == "awaiting_approval" or "pay half" in spec["text"]  # these wait for the founder (L1)
        needs_person = founder or kind == "reply_customer" and spec["skill"] != "skill_meeting_to_tasks"
        run, corr = run_of(spec, kind, needs_person), f"corr_{spec['run_id']}"
        agent = run.agent_id
        if lane.records.load("run", run.run_id) is None:
            lane.records.save("run", run.run_id, run)
            action = action_of(spec, kind)
            trace = {"action": action.model_dump(mode="json"), "verdict": {"criticality": 3 if kind == "escalate" else 2, "criticality_reasons": ["client message", "money alert" if spec["skill"] == "skill_spend_check" else "approval needed"] if kind == "escalate" else ["sent to a client"]},
                     "approval": {"assignee": "h-pamuditha" if spec["skill"] == "skill_spend_check" else spec["lead"]}}
            lane.object_store[run.trace_object_uri] = json.dumps(trace).encode()
            added += 1
        check = AccessDecision(decision_id=f"acc_{spec['run_id']}", decision="allow", rule_id="allow.capability", reason="The agent holds the capability for this action", latency_ms=6,
                               principal_id=agent, on_behalf_of=spec["lead"], action="escalate" if kind == "escalate" else "reply.draft", resource=f"chat:{spec['client'] or 'internal'}", run_id=spec["run_id"], effective_tier="L3", capabilities=["kb.read"])
        audit_rows.append(entry(lane, f"evt_{spec['run_id']}_acc", "access.decisions", check, spec["when"] + timedelta(seconds=5), "governance", corr))
        if needs_person:
            approval = ApprovalRequest(approval_id=f"apr_{spec['run_id']}", subject={"kind": "action", "ref": f"{spec['run_id']}:step_act"}, criticality=3 if founder else 2,
                                       summary_plain=f"{spec['text']}. A steward approves what goes to the client.", evidence_refs=spec["cites"], required_approvers=Approvers(tier="L1", count=1, roles=["dri"]) if founder else Approvers(tier="L2", count=1, roles=["steward"]),
                                       dri_id="h-pamuditha" if founder else spec["lead"], due_at=spec["when"] + timedelta(hours=8), expires_at=spec["when"] + timedelta(days=3))
            if lane.records.load("approval", approval.approval_id) is None:
                lane.records.save("approval", approval.approval_id, approval)
            audit_rows.append(entry(lane, f"evt_{spec['run_id']}_req", "approvals.requested", approval, spec["when"] + timedelta(seconds=8), "approvals", corr))
            if spec["outcome"] in ("resolved", "abandoned"):
                said = Decision(approval_id=approval.approval_id, decision="approve" if spec["outcome"] == "resolved" else "request_changes", decided_by=[spec["lead"]],
                                decided_at=spec["when"] + timedelta(hours=2), comment="Looks right." if spec["outcome"] == "resolved" else "Not ready, hold until the demo is fixed.")
                if not lane.records.history("decision", approval.approval_id):
                    lane.records.save("decision", approval.approval_id, said)
                audit_rows.append(entry(lane, f"evt_{spec['run_id']}_dec", "approvals.decided", said, said.decided_at, "approvals", corr))
        if spec["outcome"] == "resolved":
            sent = ActionResult(action_id=f"act_{spec['run_id']}", run_id=spec["run_id"], tool_id=TOOL[kind][0], idempotency_key=f"finebase-hq-2:{spec['run_id']}:step_act", status="succeeded",
                                external_ref=f"{spec['channel']}:{spec['run_id']}", request_hash="0" * 16, response_summary=f"Sent: {spec['text']}", attempted_at=spec["when"] + timedelta(hours=2, minutes=1), completed_at=spec["when"] + timedelta(hours=2, minutes=1, seconds=2), error=None)
            audit_rows.append(entry(lane, f"evt_{spec['run_id']}_act", "actions.executed", {**sent.model_dump(mode="json"), "outcome": "sent"}, sent.attempted_at, "worker", corr))
        audit_rows.append(entry(lane, f"evt_{spec['run_id']}_end", "runs.completed", {"run_id": spec["run_id"], "outcome": spec["outcome"], "status": spec["outcome"]}, spec["when"] + timedelta(hours=2, minutes=2 if spec["outcome"] == "resolved" else 0), "recorder", corr))
    for run_id, principal, capability, resource, reason, when in DENIES:
        deny = AccessDecision(decision_id=f"acc_{run_id}", decision="deny", rule_id="deny.no_capability", reason=reason, latency_ms=5, principal_id=principal, action=capability, resource=resource, run_id=run_id, effective_tier="L3", capabilities=["kb.read"])
        audit_rows.append(entry(lane, f"evt_{run_id}", "access.decisions", deny, when, "governance", f"corr_{run_id}"))
    for when, event_id, topic, body in sorted(audit_rows, key=lambda row: (row[0], row[1])):
        lane.audit.append(event_id, topic, body)
    return added


def seed_chats(lane) -> int:
    """One chat for each client question: their message, what the agent said, who has the chat now."""
    added = 0
    for spec in (s for s in specs() if "question" in s):
        i, run_id = spec["question"], spec["run_id"]
        conv = f"conn_{spec['channel']}:C-{spec['client']}-{i}"
        if lane.records.history(MESSAGES_KIND, conv):
            continue
        signal_id = f"sig_{run_id}"
        token = "pii_tok_" + (spec["client"].replace("_", "")[:8] + "x" * 10).ljust(18, "x")[:18] + f"{i:04d}"
        lane.records.save("signal", signal_id, Signal(signal_id=signal_id, raw_event_id=f"raw_{run_id}", kind="customer_message", channel="email" if spec["channel"] == "gmail" else "chat",
                                                      actor={"type": "customer", "ref": token}, subject={"entity_type": "conversation", "entity_ref": conv}, text_masked=CHATS[i][0], pii_tokens=[token],
                                                      sensitivity="confidential", dedup_key=f"dedup_{run_id}", conversation_id=conv, connector_id=f"conn_{spec['channel']}", domain="customer_care"))
        lane.records.save(MESSAGES_KIND, conv, ConversationMessage(signal_id=signal_id, at=spec["when"]))
        lane.records.save(RUNS_KIND, conv, OpenRun(run_id=run_id, task=task_of(spec)))
        if spec["outcome"] != "escalated" or i == 4:
            reply = CHATS[i][1] if spec["outcome"] != "awaiting_approval" else "Thanks. A steward is checking this and will confirm shortly."
            conversation_log.remember_reply(lane, conv, reply, "agent", AGENT_OF[spec["skill"]][0], run_id, signal_id)
        if i == 4:
            lane.records.save(conversation_log.STATE_KIND, conv, ConversationState(status="human", by="h-imashi", at=spec["when"] + timedelta(hours=3), note="Needs the agreement. Imashi is checking."))
        added += 1
    return added


ASKS = [("What is our Blaze bill this month and is it over budget?", "The October forecast is USD 1,260.45 against a budget of USD 900, which is 40 percent over. The Harbor test project is the main cause at USD 402.10 so far.", ["doc_blaze_oct_c1", "doc_blaze_oct_c2", "policy_spend_v2_s1"]),
        ("What did we agree with Ocean Foods about the second payment?", "The second payment of USD 3,100 was due on 20 October. They may pay half on the 20th and half on 6 November if they confirm in writing, and they did.", ["doc_wa_ocean_1022_c1", "doc_meet_ocean_1015_c2"]),
        ("Which tasks from the 26 October stand-up are still open?", "Three were open since 19 October: the Ocean Foods image fix (done 26 Oct), the Bluebird SMS check, and the Harbor repository (done). The Bluebird SMS sender name is waiting for the provider.", ["doc_meet_internal_1026_c1", "doc_slack_internal_1027_c2", "doc_slack_bluebird_1017_c1"]),
        ("When did the refund policy change and what is the limit now?", "From 1 September 2026 the window is 14 days and refunds up to USD 500 are approved automatically. Before that it was 7 days and USD 200.", ["policy_refund_v2_s1", "policy_refund_v2_s2", "policy_refund_v1_s1"])]


def seed_asks(lane, persona: str = "h-pamuditha") -> int:
    from app.api import ask_memory
    added = 0
    for i, (question, answer, cited) in enumerate(ASKS):
        conv = f"ask_hq2_{i}"
        if lane.records.history(ask_memory.KIND, conv):
            continue
        lane.records.save(ask_memory.KIND, conv, ask_memory.StoredTurn(conversation_id=conv, persona=persona, question=question, answer=answer, cited=cited, at=NOW - timedelta(hours=26 - i * 5)))
        added += 1
    return added
