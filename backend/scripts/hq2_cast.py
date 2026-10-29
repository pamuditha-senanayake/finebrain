# hq2_cast.py: who and what Finebase HQ-2 is made of: the team, the clients, the platforms. Every name is made up
# for the demo. Read by hq2_world.py (the seed files) and hq2_history.py (runs, chats, approvals). Source: [FBL] Finebase Priorities.md.
TENANT_ID = "finebase-hq-2"
CLUSTER = "client_delivery"  # the cluster runs and documents sit in; the other clusters are for the picker and the sensors

PEOPLE = {
    "h-pamuditha": {"tier": "L1", "roles": ["founder", "dri", "leader", "head_of_cs"], "delegate": None, "name": "Pamuditha Senanayake", "title": "Founder", "color": "#4338ca", "address": "sir"},
    "h-udayanga": {"tier": "L2", "roles": ["steward"], "delegate": "h-pamuditha", "name": "Udayanga Weerakoon", "title": "Steward", "color": "#0f766e"},
    "h-imashi": {"tier": "L2", "roles": ["steward"], "delegate": "h-pamuditha", "name": "Imashi Dissanayake", "title": "Steward", "color": "#b45309"},
    "h-ruwan": {"tier": "L2", "roles": ["steward", "project_lead"], "delegate": "h-pamuditha", "name": "Ruwan Jayasuriya", "title": "Project lead", "color": "#be123c"},
    "h-kavindu": {"tier": "L3", "roles": ["operator"], "delegate": "h-ruwan", "name": "Kavindu Perera", "title": "Developer", "color": "#0369a1"},
    "h-sachini": {"tier": "L3", "roles": ["operator"], "delegate": "h-ruwan", "name": "Sachini Fernando", "title": "Designer", "color": "#7e22ce"},
    "h-tharushi": {"tier": "L3", "roles": ["operator", "finance"], "delegate": "h-pamuditha", "name": "Tharushi Silva", "title": "Operations and finance", "color": "#047857"},
}

CLUSTERS = [
    {"id": "client_delivery", "name": "Client delivery", "description": "Client updates, meetings, questions and payments (A1, A2, A5).", "dri": "h-pamuditha"},
    {"id": "team_tasks", "name": "Team and tasks", "description": "Verbal tasks, owners and member progress (A3).", "dri": "h-ruwan"},
    {"id": "finance_spend", "name": "Finance and spend", "description": "Blaze plan, tools, subscriptions, US LLC banking and tax (A4, A8, A10).", "dri": "h-pamuditha"},
    {"id": "grants_docs", "name": "Grants and documents", "description": "Grants, research applications, hackathon decks and the Google Docs (A6, A7, A9).", "dri": "h-imashi"},
]

# One platform = one connection and one sensor. (id, name, source_type, sensor kind, cluster, events, personal_data)
PLATFORMS = [
    ("slack", "Slack", "chat", "chat", "client_delivery", ["message.posted"], True),
    ("whatsapp", "WhatsApp", "chat", "chat", "client_delivery", ["message.received"], True),
    ("gmail", "Gmail", "email", "inbox", "client_delivery", ["email.received"], True),
    ("meet", "Zoom and Meet transcripts", "upload", "calendar", "client_delivery", ["transcript.ready"], True),
    ("notion", "Notion board", "poll", "crm", "team_tasks", ["card.changed"], False),
    ("github", "GitHub", "webhook", "repository", "team_tasks", ["pull_request.merged"], False),
    ("stripe", "Stripe", "webhook", "payments", "finance_spend", ["invoice.paid", "payment.failed"], False),
    ("wise", "Wise", "poll", "payments", "finance_spend", ["transfer.sent"], False),
    ("mercury", "Mercury", "poll", "payments", "finance_spend", ["transaction.posted"], False),
    ("blaze", "Blaze plan billing", "email", "inbox", "finance_spend", ["invoice.received"], False),
    ("gdocs", "Google Docs", "upload", "documents", "grants_docs", ["document.changed"], False),
    ("gdrive", "Google Drive", "upload", "documents", "grants_docs", ["file.added"], False),
]

# (id, name, project, platform the client talks on, lead, started, monthly fee in USD)
CLIENTS = [
    ("lanka_print", "Lanka Print Co.", "Order tracking portal", "slack", "h-ruwan", "2026-07-06", 4800),
    ("ocean_foods", "Ocean Foods", "Mobile ordering app", "whatsapp", "h-ruwan", "2026-08-03", 6200),
    ("bluebird", "Bluebird Clinics", "Appointment booking", "slack", "h-imashi", "2026-08-17", 5400),
    ("kandy_tea", "Kandy Tea Traders", "Online storefront", "whatsapp", "h-udayanga", "2026-09-01", 3900),
    ("harbor", "Harbor Logistics", "Dispatch dashboard", "slack", "h-ruwan", "2026-09-14", 7100),
    ("nila", "Nila Learning", "Learning platform pilot", "gmail", "h-imashi", "2026-10-05", 4300),
]
