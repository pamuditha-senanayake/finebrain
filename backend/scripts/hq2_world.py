# hq2_world.py: builds the sample files the Finebase HQ-2 API starts from (samples/hq2_*.json): the tenant, its platforms as
# connectors and sensors, the A1 to A5 skills and agents, policies with dated versions, every document as knowledge, the
# obligations readiness watches. Deterministic: the same code gives the same files. Run: uv run python -m scripts.hq2_world
# Used by: seed_hq2.py, tests/test_hq2_seed.py. Uses: hq2_cast.py, hq2_docs.py.
import json
import re
from pathlib import Path

from scripts.hq2_cast import CLIENTS, CLUSTER, CLUSTERS, PEOPLE, PLATFORMS, TENANT_ID
from scripts.hq2_docs import DOCS, FACTS, POLICIES

# Config
SAMPLES = Path(__file__).resolve().parents[1] / "samples"
ZONE = "+05:30"
FOUNDER = "h-pamuditha"
FILING_RULES = json.loads((SAMPLES / "hq_tenant.json").read_text())["seed_overrides"]["filing_rules"]
AGENTS = {  # id: (name, description, capabilities, job)
    "agent_update_drafter": ("Update drafter", "Turns a meeting or a client message into a draft update for a steward to approve (A1, A2).", ["kb.read", "reply.draft"], "A1"),
    "agent_task_tracker": ("Task tracker", "Turns a transcript into tasks with owners, and reminds owners (A3).", ["kb.read", "reply.draft"], "A3"),
    "agent_spend_watcher": ("Spend watcher", "Reads bills and subscriptions against the budget and raises an alert (A4).", ["kb.read"], "A4"),
    "agent_docs_writer": ("Docs writer", "Drafts grant applications, hackathon decks and updates to the Google Docs from what the team has built (A6, A7, A9).", ["kb.read"], "A6"),
    "agent_client_qa": ("Client questions", "Answers clarification and payment questions from the documents (A5).", ["kb.read", "reply.draft"], "A5"),
}
SKILLS = [  # (id, name, tools, steps, agent, activity, channels, keywords, description)
    ("skill_client_update", "Client update", ["reply_customer", "escalate"],
     ["Read the project's last update and what changed since in the meeting transcript, Slack or WhatsApp.", "Draft a short written update, with a line on what is next.",
      "Propose reply_customer with the draft in the client's own channel. A steward approves it before it is sent.", "If the client asked for something the project lead has not agreed, use escalate."],
     "agent_update_drafter", "act_client_update", ["chat", "email"], ["update", "status", "progress", "video"], "A client asks for an update, or a week passes without one"),
    ("skill_meeting_to_tasks", "Transcript to tasks", ["reply_customer", "escalate"],
     ["Read the transcript and list every task said out loud, with its owner and due date.", "Check the open tasks so that nothing is listed twice.",
      "Propose reply_customer to post the task list to the team channel and remind the owners.", "If a task has no clear owner, use escalate to the project lead."],
     "agent_task_tracker", "act_meeting_followup", ["upload"], ["transcript", "meeting", "tasks"], "A meeting transcript arrives"),
    ("skill_spend_check", "Spend check", ["escalate"],
     ["Read this month's bills and subscriptions and last month's spend.", "Compare with the budget in the spend policy.", "If spend is more than 20 percent over budget, or a new subscription is above USD 50, use escalate with the figures."],
     "agent_spend_watcher", "act_spend_check", ["poll"], ["blaze", "subscription", "spend", "budget"], "A bill, an invoice or a bank transaction arrives"),
    ("skill_client_questions", "Client questions", ["reply_customer", "escalate"],
     ["Find the agreement, invoice or payment the client asks about in the documents.", "Answer from the payment terms and the refund policy, citing them.", "If the documents do not answer, use escalate."],
     "agent_client_qa", "act_client_question", ["chat", "webhook"], ["invoice", "payment", "pay", "refund", "owe"], "A client asks about an invoice, a payment or what was agreed"),
    ("skill_member_progress", "Member progress check", ["reply_customer", "escalate"],
     ["Read the merged work and the task list for each member.", "Find tasks with no progress for 3 days, or work merged that was never posted.",
      "Propose reply_customer to ask the owner for a short progress note in the team channel.", "If the same task stays quiet after the reminder, use escalate to the project lead."],
     "agent_task_tracker", "act_member_progress", ["webhook"], ["progress", "merged", "pull", "blocked"], "A task has had no progress for 3 days"),
    ("skill_grant_docs", "Grant and document draft", ["escalate"],
     ["Read the call, the last draft and what the team has built since.", "List what is missing against the call: summary, budget, letters, open results plan.",
      "Use escalate to hand the missing list and the draft to the owner of the application."],
     "agent_docs_writer", "act_grant_docs", ["upload"], ["grant", "application", "deck", "hackathon", "docs"], "A grant call, a deck or a Google Doc needs work"),
]
ACTIVITY_CLUSTER = {"act_client_update": "client_delivery", "act_client_question": "client_delivery", "act_meeting_followup": "team_tasks", "act_member_progress": "team_tasks",
                    "act_spend_check": "finance_spend", "act_grant_docs": "grants_docs"}
LINKS = {"skill_client_update": ["policy_client_comms", "policy_data"], "skill_meeting_to_tasks": ["policy_tasks", "policy_data"],  # policies that govern each skill
         "skill_spend_check": ["policy_spend"], "skill_client_questions": ["policy_refund", "policy_payments"],
         "skill_member_progress": ["policy_tasks"], "skill_grant_docs": ["policy_data"]}
SCHEME = {"slack": "slack", "whatsapp": "whatsapp", "gmail": "gmail", "meet": "meet", "notion": "notion", "github": "github", "stripe": "stripe", "wise": "wise",
          "mercury": "mercury", "blaze": "blaze", "gdocs": "gdocs", "gdrive": "gdrive"}


def stamp(day: str, hour: int = 9) -> str:
    return f"{day}T{hour:02d}:00:00{ZONE}"


def uri_of(platform: str, title: str) -> str:
    return f"{SCHEME[platform]}://finebase-labs/{re.sub(r'[^A-Za-z0-9_-]+', '_', title).strip('_')}.txt"


def item(item_id, kind, text, doc_id, uri, span, valid_from, valid_to, sens, domain, platform, **more):
    return {"item_id": item_id, "kind": kind, "text": text, "source": {"document_id": doc_id, "uri": uri, "span": span}, "valid_from": valid_from, "valid_to": valid_to,
            "recorded_at": valid_from, "verified_by": more.pop("verified_by", None), "version_ref": more.pop("version_ref", None), "score": more.pop("score", 0.0),
            "sensitivity": sens, "domain": domain, "platform": platform, **more}


def policy_documents() -> list[dict]:
    """One document per policy version: (doc id, platform, title, domain, sensitivity, date, paragraphs)."""
    return [{"id": f"doc_{key}_v{v}", "platform": "gdocs", "title": f"{name} v{v}", "domain": "operations", "sensitivity": "internal", "date": start, "paragraphs": lines}
            for key, name, _, versions in POLICIES for v, start, _, lines in versions]


def knowledge() -> list[dict]:
    items = []
    for key, name, _, versions in POLICIES:
        for v, start, end, lines in versions:
            doc_id, uri, at = f"doc_{key}_v{v}", uri_of("gdocs", f"{name} v{v}"), 0
            for n, line in enumerate(lines, start=1):
                items.append(item(f"{key}_v{v}_s{n}", "policy", line, doc_id, uri, f"{at}:{at + len(line)}", stamp(start), stamp(end) if end else None, "internal", "operations", "gdocs",
                                  verified_by=FOUNDER, score=0.9, version_ref={"id": key, "version": v, "branch": "main", "commit_id": f"cmt_hq2_{key}_{v}"}))
                at += len(line) + 1
    for doc_id, platform, title, domain, sens, day, paragraphs in DOCS:
        for n, para in enumerate(paragraphs, start=1):
            items.append(item(f"{doc_id}_c{n}", "chunk", f"{title}: {para}", doc_id, uri_of(platform, title), f"chunk:{n}", stamp(day), None, sens, domain, platform, title=title))
    return items


def payments() -> dict:
    """Stripe payments for each client, a first payment and one a month: pay_FB_YYYYMMDD_NNNN."""
    found = {}
    for n, (_, _, _, _, _, started, fee) in enumerate(CLIENTS, start=1):
        for month in ("2026-08", "2026-09", "2026-10"):
            if month >= started[:7]:
                day = started[:7] + "-" + started[8:] if month == started[:7] else f"{month}-{(n * 3) % 20 + 5:02d}"
                found[f"pay_FB_{day.replace('-', '')}_{n:04d}"] = {"amount_minor": fee * 100 // (2 if month == started[:7] else 1), "paid_at": stamp(day, 0)}
    return found


def connectors() -> dict:
    made = {"_about": "Finebase HQ-2: test-only secrets. Every platform is one connection; real secrets live in Secrets Manager.",
            "conn_upload_console": {"grant_id": "grant_upload_all", "grant_active": True, "source_type": "upload", "secret": "test-only-secret-upload"}}
    for pid, _, source, *_ in PLATFORMS:
        made[f"conn_{pid}"] = {"grant_id": f"grant_{pid}_read", "grant_active": pid != "notion", "source_type": source, "secret": f"test-only-secret-{pid}"}  # the Notion board is the one switched off (A11)
    return made


def rules() -> list[dict]:
    return [{"rule_id": f"rr_{skill[5].removeprefix('act_')}", "description": skill[8], "activity_id": skill[5], "kinds": ["customer_message", "billing_event", "document_arrived"], "channels": skill[6],
             "required_entities": [], "keywords": skill[7], "skill_id": skill[0], "agent_id": skill[4], "base_criticality": 2 if "reply_customer" in skill[2] else 1,
             "due_hours": 4, "priority": 3} for skill in SKILLS]


def build_world() -> dict:
    skills = [{"id": s[0], "version": 1, "commit_id": f"cmt_hq2_{s[0]}", "name": s[1], "allowed_tools": s[2], "steps": s[3]} for s in SKILLS]
    agents = {aid: {"type": "agent", "id": aid, "capabilities": caps, "tier": "L3"} for aid, (_, _, caps, _) in AGENTS.items()}
    policy = {"policy_ref": {"id": "policy_refund", "version": 2, "branch": "main", "commit_id": "cmt_hq2_policy_refund_2"}, "window_days": 14,
              "auto_limit": {"amount_minor": 50000, "currency": "USD"}, "escalation": {"criticality": 3, "approvers": {"tier": "L1", "count": 1, "roles": ["head_of_cs"]}}}
    return {"_about": "Finebase HQ-2: the world its API starts from, replacing the golden refund world. Made by scripts/hq2_world.py; do not edit by hand.",
            "cluster_id": CLUSTER, "env": "production", "connectors": connectors(), "resolver_rules": rules(), "skills": skills, "agents": agents, "refund_policy": policy,
            "payments": payments(), "knowledge": knowledge()}


def build_tenant() -> dict:
    sensors = {f"conn_{pid}": {"name": name, "kind": kind, "cluster": cluster, "events": events, "subscribers": [s[4] for s in SKILLS if source in s[6]], "personal_data": personal}
               for pid, name, source, kind, cluster, events, personal in PLATFORMS}
    sensors["conn_upload_console"] = {"name": "Console uploads", "kind": "documents", "cluster": "grants_docs", "events": ["document.uploaded"], "subscribers": [], "personal_data": False}
    names = {key: {"name": name, "dri": FOUNDER, "skills": [s for s, keys in LINKS.items() if key in keys]} for key, name, *_ in POLICIES}
    return {"_about": "Finebase HQ-2: the second live tenant, on its own port (HQ_TENANT_FILE=hq2_tenant.json). Everything in it is made up for demos. Made by scripts/hq2_world.py.",
            "tenant": {"id": TENANT_ID, "name": "Finebase HQ-2", "currency": "USD", "timezone": "Asia/Colombo", "locale": "en-US", "brand": {"primary": "#0f766e", "mark": "H2"}},
            "sample_files": {"world": "hq2_world.json", "obligations": "hq2_obligations.json", "counts": "hq2_counts.json"},
            "seed_overrides": {"tenant_id": TENANT_ID, "env": "production", "commons": [], "filing_rules": FILING_RULES}, "people": PEOPLE, "clusters": CLUSTERS, "sensors": sensors,
            "graph_labels": {"agents": {aid: {"name": a[0], "description": a[1], "kind": "worker", "dri": FOUNDER} for aid, a in AGENTS.items()}, "policies": names, "skill_dri": FOUNDER}}


def build_obligations() -> dict:
    def grant(source, scope):
        return {"source": source, "scope": scope, "retention_days": 90, "agents": ["agent_client_qa"], "revoke": "Revoke any time on the Evidence page. Access ends by itself after 90 days."}
    return {"_about": "Finebase HQ-2: sample obligations (A4, A6, A8, A10). Dates and evidence are made up.", "obligations": [
        {"id": "ob_blaze_review", "title": "Monthly spend review", "jurisdiction": "Internal", "category": "internal", "dri": FOUNDER, "due": {"every": "month", "day": 5}, "prepare_days": 5,
         "note": "Spend policy: review Blaze and subscriptions on the 5th.", "items": [
             {"key": "cloud", "label": "Blaze plan bill", "predicate": "cloud_spend", "grant": grant("Blaze billing emails", "Read the monthly bill, nothing else")},
             {"key": "subs", "label": "Tools and subscriptions total", "predicate": "subscription_total"}]},
        {"id": "ob_de_annual", "title": "Delaware annual report and franchise tax", "jurisdiction": "Delaware, USA", "category": "statutory", "dri": FOUNDER, "due": {"every": "year", "month": 3, "day": 1},
         "prepare_days": 30, "note": "Due 1 March each year (A8).", "items": [{"key": "report", "label": "Annual report", "predicate": "de_annual_report"}, {"key": "tax", "label": "Franchise tax receipt", "predicate": "franchise_tax_paid"}]},
        {"id": "ob_5472", "title": "Form 5472 and pro-forma 1120", "jurisdiction": "United States", "category": "tax", "dri": FOUNDER, "due": {"every": "year", "month": 4, "day": 15},
         "prepare_days": 60, "note": "Due 15 April; a missing form costs USD 25,000 (A10).", "items": [
             {"key": "statements", "label": "Bank statements for the year", "predicate": "bank_statements_year", "grant": grant("Mercury statements", "Read the yearly statements, nothing else")},
             {"key": "form", "label": "Filed form", "predicate": "form_5472_filed"}]},
        {"id": "ob_contractors", "title": "Contractor payments", "jurisdiction": "Internal", "category": "internal", "dri": "h-tharushi", "due": {"every": "month", "day": 28}, "prepare_days": 5,
         "note": "Contractors are paid from Wise on the 28th.", "items": [{"key": "total", "label": "Payment total", "predicate": "contractor_payments_total"}]},
        {"id": "ob_grant_orf", "title": "Open Research Fund application", "jurisdiction": "Grant (sample)", "category": "grant", "dri": "h-imashi", "due": {"every": "year", "month": 11, "day": 30},
         "prepare_days": 45, "note": "Autumn call closes 30 November (A6).", "items": [
             {"key": "summary", "label": "Two page summary", "predicate": "grant_summary"}, {"key": "budget", "label": "Budget", "predicate": "grant_budget"},
             {"key": "letter", "label": "Partner school letter", "predicate": "partner_letter"}]}],
        "rules": [{"id": "rr_spend", "target": "Spend and subscriptions", "requires": "Each bill proven by a verified fact for that month", "check_every": "Hourly", "escalation_days": [7, 3, 1]},
                  {"id": "rr_filings", "target": "US LLC filings", "requires": "Each item proven before the due day", "check_every": "Hourly", "escalation_days": [60, 30, 14, 7]}],
        "risks": [{"id": "risk_5472", "title": "Form 5472 is filed late", "likelihood": "low", "impact": "high", "owner": FOUNDER, "mitigation": "Readiness asks for the bank statements 60 days before.", "linked_obligation": "ob_5472"},
                  {"id": "risk_blaze", "title": "Blaze spend runs past the budget", "likelihood": "high", "impact": "medium", "owner": "h-tharushi", "mitigation": "The spend watcher raises an alert at 20 percent over.", "linked_obligation": "ob_blaze_review"}]}


def build_counts() -> dict:
    return {"_about": "Finebase HQ-2: 11 made-up weekly counts ending on the week of 26 October.", "weeks_ending": "2026-10-26", "series": [
        {"metric": "Requests", "segment": "Client update, Slack", "weeks": [5, 6, 5, 7, 6, 8, 7, 6, 8, 9, 7]},
        {"metric": "Requests", "segment": "Client update, WhatsApp", "weeks": [3, 4, 3, 3, 4, 5, 4, 5, 4, 5, 6]},
        {"metric": "Requests", "segment": "Client questions, chat", "weeks": [2, 1, 2, 3, 2, 2, 3, 2, 3, 3, 4]},
        {"metric": "Escalations", "segment": "Task tracker, transcripts", "weeks": [1, 0, 1, 1, 2, 1, 1, 2, 2, 1, 3]}]}


def write_samples() -> list[Path]:
    files = {"hq2_tenant.json": build_tenant(), "hq2_world.json": build_world(), "hq2_obligations.json": build_obligations(), "hq2_counts.json": build_counts()}
    for name, body in files.items():
        (SAMPLES / name).write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
    return [SAMPLES / name for name in files]


if __name__ == "__main__":
    for path in write_samples():
        print("wrote", path.relative_to(SAMPLES.parent))
