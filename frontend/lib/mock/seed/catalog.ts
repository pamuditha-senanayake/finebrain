// Curated catalog for the Finebase Labs tenant. Every date and rule here is SAMPLE data.
import type { Criticality, Sensitivity } from "@/contracts";
import type { ActivityDef } from "../types";

export const CLUSTERS = [
  { id: "finebase-platform", name: "Finebase Platform", description: "Software services and SaaS products sold and managed on the Finebase platform.", status: "active" as const, dri: "h-founder" },
  { id: "finance-compliance", name: "Finance and Compliance", description: "Thin cluster that protects the legal entity: tax, statutory filings, renewals, receivables.", status: "active" as const, dri: "h-fd" },
  { id: "people", name: "People", description: "Planned: hiring, onboarding staff, leave and payroll inputs.", status: "planned" as const, dri: null },
  { id: "product-engineering", name: "Product Engineering", description: "Planned: roadmap, delivery health and release quality.", status: "planned" as const, dri: null },
  { id: "procurement", name: "Procurement", description: "Planned: vendor selection, purchase orders and contract intake.", status: "planned" as const, dri: null },
];

export const HUMANS = [
  { id: "h-founder", name: "Nadeesha Perera", title: "Founder", tier: "L1", roles: ["founder", "dri"], clearance: "restricted", driOf: ["cluster:finebase-platform"], max: 4, color: "#4338ca" },
  { id: "h-fd", name: "Ruwan Jayasinghe", title: "Finance Director", tier: "L1", roles: ["finance", "dri"], clearance: "restricted", driOf: ["cluster:finance-compliance", "obligations"], max: 4, color: "#0369a1" },
  { id: "h-hcs", name: "Ishara Fernando", title: "Head of Customer Success", tier: "L1", roles: ["customer-success", "dri"], clearance: "confidential", driOf: ["refunds", "care", "website"], max: 4, color: "#be123c" },
  { id: "h-ks", name: "Dilini Wickramasinghe", title: "Knowledge Steward", tier: "L2", roles: ["knowledge-steward"], clearance: "confidential", driOf: ["library", "ground-truth"], max: 2, color: "#047857" },
  { id: "h-aiops", name: "Kasun Bandara", title: "AI Operations Lead", tier: "L2", roles: ["ai-ops"], clearance: "confidential", driOf: ["skills", "resolver", "loops"], max: 2, color: "#b45309" },
  { id: "h-sec", name: "Tharindu Silva", title: "Security Officer", tier: "L2", roles: ["security"], clearance: "restricted", driOf: ["security", "access"], max: 2, color: "#6d28d9" },
  { id: "h-op", name: "Amaya Gunawardena", title: "Customer Care Operator", tier: "L3", roles: ["care-operator"], clearance: "internal", driOf: [], max: 0, color: "#0f766e" },
  { id: "h-research", name: "Research Analyst", title: "Research program", tier: "L2", roles: ["research"], clearance: "internal", driOf: [], max: 0, color: "#475569" },
] as const;

export const TOOLS: { id: string; label: string; capability: string; sensitivity: Sensitivity }[] = [
  { id: "tool:chat.reply", label: "chat.reply", capability: "reply:customer", sensitivity: "internal" },
  { id: "tool:inbox.reply", label: "support-inbox.reply", capability: "reply:customer", sensitivity: "internal" },
  { id: "tool:billing.refund", label: "billing.refund", capability: "refund:issue", sensitivity: "internal" },
  { id: "tool:billing.credit", label: "billing.credit", capability: "credit:goodwill", sensitivity: "internal" },
  { id: "tool:billing.retry", label: "billing.retry-charge", capability: "billing:retry", sensitivity: "internal" },
  { id: "tool:crm.update", label: "crm.update", capability: "crm:write", sensitivity: "internal" },
  { id: "tool:calendar.book", label: "calendar.book", capability: "calendar:write", sensitivity: "internal" },
  { id: "tool:cms.publish", label: "cms.publish", capability: "cms:publish", sensitivity: "internal" },
  { id: "tool:experiments.create", label: "experiments.create", capability: "experiments:run", sensitivity: "internal" },
  { id: "tool:reviews.reply", label: "reviews.reply", capability: "reviews:reply", sensitivity: "public" },
  { id: "tool:status.post", label: "statuspage.post", capability: "status:publish", sensitivity: "public" },
  { id: "tool:evidence.request", label: "evidence.request", capability: "evidence:request", sensitivity: "confidential" },
  { id: "tool:finance-inbox.read", label: "finance-inbox.read", capability: "finance:read", sensitivity: "restricted" },
  { id: "tool:graph.commit", label: "graph.commit", capability: "graph:draft", sensitivity: "confidential" },
];

type AgentDef = {
  id: string;
  name: string;
  kind: "worker" | "supervisor";
  cluster: string;
  description: string;
  autonomy: "trainee" | "supervised" | "autonomous";
  capabilities: string[];
  level: Sensitivity;
  sensors: string[];
  templates: string[];
  dri: string;
  throughput: number;
};

export const AGENTS: AgentDef[] = [
  { id: "a-care", name: "Care Agent", kind: "worker", cluster: "finebase-platform", description: "Answers customer chat and email, grants small goodwill credits.", autonomy: "autonomous", capabilities: ["reply:customer", "credit:goodwill", "crm:write"], level: "internal", sensors: ["s-chat", "s-support-inbox", "s-usage"], templates: ["tpl-care-weekly", "tpl-data-requests"], dri: "h-hcs", throughput: 14 },
  { id: "a-refund", name: "Refund Agent", kind: "worker", cluster: "finebase-platform", description: "Handles refund and cancellation requests inside the refund policy.", autonomy: "supervised", capabilities: ["reply:customer", "refund:issue", "billing:read"], level: "confidential", sensors: ["s-support-inbox", "s-payments"], templates: ["tpl-refund-register"], dri: "h-hcs", throughput: 3 },
  { id: "a-billing", name: "Billing Agent", kind: "worker", cluster: "finance-compliance", description: "Subscription billing, failed payment recovery, receivables and expenses.", autonomy: "autonomous", capabilities: ["billing:read", "billing:retry", "reply:customer"], level: "confidential", sensors: ["s-payments", "s-bank-feed", "s-card-feed", "s-finance-inbox"], templates: ["tpl-revenue-health", "tpl-receivables", "tpl-expense-log"], dri: "h-fd", throughput: 6 },
  { id: "a-sales", name: "Sales Agent", kind: "worker", cluster: "finebase-platform", description: "Qualifies leads, follows up and drafts quotes for service projects.", autonomy: "supervised", capabilities: ["crm:write", "reply:customer"], level: "internal", sensors: ["s-lead-forms", "s-chat", "s-support-inbox"], templates: ["tpl-pipeline"], dri: "h-founder", throughput: 4 },
  { id: "a-scheduler", name: "Scheduler Agent", kind: "worker", cluster: "finebase-platform", description: "Arranges demos, discovery calls and sprint reviews, turns notes into actions.", autonomy: "autonomous", capabilities: ["calendar:write", "reply:customer"], level: "internal", sensors: ["s-calendars", "s-booking", "s-transcripts"], templates: ["tpl-meeting-log", "tpl-action-log"], dri: "h-founder", throughput: 5 },
  { id: "a-onboarding", name: "Onboarding Agent", kind: "worker", cluster: "finebase-platform", description: "Runs client onboarding checklists for service projects.", autonomy: "supervised", capabilities: ["crm:write", "reply:customer"], level: "internal", sensors: ["s-contracts", "s-crm"], templates: ["tpl-onboarding"], dri: "h-hcs", throughput: 1.5 },
  { id: "a-delivery", name: "Delivery Agent", kind: "worker", cluster: "finebase-platform", description: "Tracks retainer SLAs and writes client status reports.", autonomy: "autonomous", capabilities: ["reply:customer"], level: "internal", sensors: ["s-tracker", "s-repo", "s-uptime"], templates: ["tpl-client-status"], dri: "h-founder", throughput: 2 },
  { id: "a-web", name: "Web Content Agent", kind: "worker", cluster: "finebase-platform", description: "Updates website content and release notes.", autonomy: "supervised", capabilities: ["cms:publish"], level: "internal", sensors: ["s-cms", "s-releases"], templates: ["tpl-content-log"], dri: "h-hcs", throughput: 1 },
  { id: "a-insights", name: "Insights Agent", kind: "worker", cluster: "finebase-platform", description: "Finds UX friction and proposes experiments.", autonomy: "supervised", capabilities: ["experiments:run"], level: "internal", sensors: ["s-clarity", "s-analytics", "s-clicks"], templates: ["tpl-experiments"], dri: "h-hcs", throughput: 0.8 },
  { id: "a-reputation", name: "Reputation Agent", kind: "worker", cluster: "finebase-platform", description: "Replies to reviews and NPS feedback.", autonomy: "supervised", capabilities: ["reviews:reply"], level: "public", sensors: ["s-reviews", "s-nps"], templates: ["tpl-voc"], dri: "h-hcs", throughput: 1.2 },
  { id: "a-incident", name: "Incident Agent", kind: "worker", cluster: "finebase-platform", description: "Drafts outage communication.", autonomy: "trainee", capabilities: ["status:publish"], level: "internal", sensors: ["s-uptime", "s-errors"], templates: ["tpl-incident"], dri: "h-founder", throughput: 0.3 },
  { id: "a-compliance", name: "Compliance Agent", kind: "worker", cluster: "finance-compliance", description: "Prepares tax and statutory readiness and tracks renewals. Humans file.", autonomy: "supervised", capabilities: ["evidence:request", "billing:read"], level: "restricted", sensors: ["s-obligations", "s-accounting", "s-contracts", "s-vendor-invoices", "s-certs"], templates: ["tpl-obligations", "tpl-renewals"], dri: "h-fd", throughput: 1.5 },
  { id: "a-quality", name: "Quality Supervisor", kind: "supervisor", cluster: "finebase-platform", description: "Reviews L3 runs overnight, classifies failures and drafts fixes.", autonomy: "autonomous", capabilities: ["graph:review", "graph:draft"], level: "confidential", sensors: [], templates: ["tpl-improvement"], dri: "h-aiops", throughput: 2 },
  { id: "a-librarian", name: "Librarian", kind: "supervisor", cluster: "finebase-platform", description: "Keeps ground truth fresh, finds conflicts and proposes resolutions.", autonomy: "autonomous", capabilities: ["graph:review", "graph:draft"], level: "restricted", sensors: [], templates: ["tpl-freshness"], dri: "h-ks", throughput: 1 },
  { id: "a-sentinel", name: "Security Sentinel", kind: "supervisor", cluster: "finebase-platform", description: "Reviews access, flags denials and proposes grants.", autonomy: "autonomous", capabilities: ["graph:review", "graph:draft", "access:review"], level: "restricted", sensors: [], templates: ["tpl-access-review"], dri: "h-sec", throughput: 1 },
];

export type SkillDef = {
  id: string;
  name: string;
  agent: string;
  version: number;
  trigger: string;
  steps: [string, "judgment" | "tool" | "retrieval" | "quality_gate", string | null][];
  tools: string[];
  policies: string[];
  caps: string[];
  outputs: string[];
  fields: string[];
  health: [number, number, number];
};

export const SKILLS: SkillDef[] = [
  { id: "care-answer", name: "Answer product question", agent: "a-care", version: 7, trigger: "Customer message classified as product question", steps: [["Retrieve facts for the product area", "retrieval", null], ["Draft answer with citations", "judgment", null], ["Check tone and grounding", "quality_gate", null], ["Send reply", "tool", "tool:chat.reply"]], tools: ["tool:chat.reply", "tool:inbox.reply"], policies: ["public-reply-tone", "pii-masking"], caps: ["reply:customer"], outputs: ["Reply"], fields: ["tpl-care-weekly.answered"], health: [0.93, 0.88, 0.91] },
  { id: "care-goodwill", name: "Goodwill credit", agent: "a-care", version: 2, trigger: "Customer reports service issue with usage impact", steps: [["Retrieve usage impact", "retrieval", null], ["Decide credit within cap", "judgment", null], ["Apply credit", "tool", "tool:billing.credit"]], tools: ["tool:billing.credit"], policies: ["goodwill-credit"], caps: ["credit:goodwill"], outputs: ["Credit note"], fields: ["tpl-care-weekly.credits"], health: [0.9, 0.84, 0.86] },
  { id: "refund-standard", name: "Refund inside policy", agent: "a-refund", version: 4, trigger: "Refund or cancellation request", steps: [["Retrieve purchase and refund policy", "retrieval", null], ["Check window and threshold", "judgment", null], ["Access check for refund tool", "quality_gate", null], ["Issue refund", "tool", "tool:billing.refund"], ["Confirm to customer", "tool", "tool:inbox.reply"]], tools: ["tool:billing.refund", "tool:inbox.reply"], policies: ["refund-window", "refund-auto-threshold"], caps: ["refund:issue", "reply:customer"], outputs: ["Refund", "Confirmation"], fields: ["tpl-refund-register.refunds"], health: [0.86, 0.79, 0.62] },
  { id: "billing-dunning", name: "Failed payment recovery", agent: "a-billing", version: 3, trigger: "Payment gateway reports a failed charge", steps: [["Retrieve customer billing history", "retrieval", null], ["Send reminder", "tool", "tool:inbox.reply"], ["Retry charge after 3 days", "tool", "tool:billing.retry"]], tools: ["tool:billing.retry", "tool:inbox.reply"], policies: ["write-off"], caps: ["billing:retry"], outputs: ["Reminder", "Retry"], fields: ["tpl-revenue-health.recovered"], health: [0.81, 0.9, 0.84] },
  { id: "billing-receivables", name: "Receivables chasing", agent: "a-billing", version: 2, trigger: "Invoice overdue by 7 days", steps: [["Retrieve invoice and bank feed", "retrieval", null], ["Draft reminder", "judgment", null], ["Send reminder", "tool", "tool:inbox.reply"]], tools: ["tool:inbox.reply"], policies: ["write-off"], caps: ["reply:customer"], outputs: ["Reminder"], fields: ["tpl-receivables.aging"], health: [0.88, 0.9, 0.87] },
  { id: "billing-expenses", name: "Expense capture", agent: "a-billing", version: 1, trigger: "Receipt arrives in finance inbox", steps: [["Extract receipt", "retrieval", null], ["Categorise", "judgment", null], ["Log expense", "tool", "tool:crm.update"]], tools: ["tool:crm.update"], policies: ["data-retention"], caps: ["billing:read"], outputs: ["Expense row"], fields: ["tpl-expense-log.rows"], health: [0.92, 0.93, 0.9] },
  { id: "sales-qualify", name: "Lead qualification", agent: "a-sales", version: 5, trigger: "New lead form or chat with buying intent", steps: [["Retrieve company facts", "retrieval", null], ["Score lead", "judgment", null], ["Update CRM", "tool", "tool:crm.update"]], tools: ["tool:crm.update"], policies: ["pii-masking"], caps: ["crm:write"], outputs: ["Lead score"], fields: ["tpl-pipeline.qualified"], health: [0.87, 0.85, 0.83] },
  { id: "sales-quote", name: "Quote for service project", agent: "a-sales", version: 2, trigger: "Qualified lead asks for a quote", steps: [["Retrieve rate card", "retrieval", null], ["Draft quote", "judgment", null], ["Check against rate card", "quality_gate", null]], tools: ["tool:crm.update"], policies: ["pricing-change"], caps: ["crm:write"], outputs: ["Quote draft"], fields: ["tpl-pipeline.quotes"], health: [0.78, 0.74, 0.8] },
  { id: "scheduler-booking", name: "Meeting arrangement", agent: "a-scheduler", version: 4, trigger: "Request for demo, discovery call or sprint review", steps: [["Retrieve calendars", "retrieval", null], ["Propose slots", "judgment", null], ["Book meeting", "tool", "tool:calendar.book"]], tools: ["tool:calendar.book"], policies: [], caps: ["calendar:write"], outputs: ["Invite"], fields: ["tpl-meeting-log.booked"], health: [0.95, 0.94, 0.93] },
  { id: "scheduler-notes", name: "Notes to action items", agent: "a-scheduler", version: 2, trigger: "Meeting transcript available", steps: [["Read transcript", "retrieval", null], ["Extract actions", "judgment", null], ["Log actions", "tool", "tool:crm.update"]], tools: ["tool:crm.update"], policies: ["pii-masking"], caps: ["crm:write"], outputs: ["Action list"], fields: ["tpl-action-log.actions"], health: [0.89, 0.86, 0.88] },
  { id: "onboarding-checklist", name: "Client onboarding", agent: "a-onboarding", version: 3, trigger: "Contract signed", steps: [["Retrieve contract scope", "retrieval", null], ["Create checklist", "judgment", null], ["Request access grants", "tool", "tool:crm.update"]], tools: ["tool:crm.update"], policies: ["access-review"], caps: ["crm:write"], outputs: ["Checklist"], fields: ["tpl-onboarding.items"], health: [0.84, 0.82, 0.8] },
  { id: "delivery-status", name: "Client status report", agent: "a-delivery", version: 6, trigger: "Weekly on Friday", steps: [["Retrieve tracker and uptime", "retrieval", null], ["Draft report", "judgment", null], ["Send report", "tool", "tool:inbox.reply"]], tools: ["tool:inbox.reply"], policies: ["public-reply-tone"], caps: ["reply:customer"], outputs: ["Report"], fields: ["tpl-client-status.report"], health: [0.91, 0.89, 0.9] },
  { id: "web-content-update", name: "Website content update", agent: "a-web", version: 3, trigger: "Content request or product release", steps: [["Retrieve release notes", "retrieval", null], ["Draft copy", "judgment", null], ["Publish on general pages", "tool", "tool:cms.publish"]], tools: ["tool:cms.publish"], policies: ["pricing-change", "public-reply-tone"], caps: ["cms:publish"], outputs: ["Page change"], fields: ["tpl-content-log.changes"], health: [0.88, 0.86, 0.87] },
  { id: "insights-experiment", name: "UX experiment proposal", agent: "a-insights", version: 2, trigger: "Friction signal above threshold", steps: [["Read Clarity and analytics", "retrieval", null], ["Form hypothesis", "judgment", null], ["Create experiment on sandbox branch", "tool", "tool:experiments.create"]], tools: ["tool:experiments.create"], policies: ["pricing-change"], caps: ["experiments:run"], outputs: ["Experiment"], fields: ["tpl-experiments.proposed"], health: [0.8, 0.77, 0.79] },
  { id: "reputation-reply", name: "Public review reply", agent: "a-reputation", version: 2, trigger: "New review or NPS comment", steps: [["Retrieve account context", "retrieval", null], ["Draft reply", "judgment", null], ["Tone gate", "quality_gate", null], ["Post reply", "tool", "tool:reviews.reply"]], tools: ["tool:reviews.reply"], policies: ["public-reply-tone"], caps: ["reviews:reply"], outputs: ["Reply"], fields: ["tpl-voc.replies"], health: [0.86, 0.83, 0.85] },
  { id: "incident-comms", name: "Outage communication", agent: "a-incident", version: 1, trigger: "Uptime monitor alert lasting 5 minutes", steps: [["Retrieve incident facts", "retrieval", null], ["Draft statement", "judgment", null], ["Post status", "tool", "tool:status.post"]], tools: ["tool:status.post"], policies: ["public-reply-tone"], caps: ["status:publish"], outputs: ["Status post"], fields: ["tpl-incident.statement"], health: [0.72, 0.7, 0.75] },
  { id: "compliance-readiness", name: "Obligation readiness", agent: "a-compliance", version: 4, trigger: "Readiness scheduler finds a gap", steps: [["Compare required with available evidence", "retrieval", null], ["Decide dispatch or request", "judgment", null], ["Request evidence", "tool", "tool:evidence.request"]], tools: ["tool:evidence.request", "tool:finance-inbox.read"], policies: ["vat-evidence"], caps: ["evidence:request"], outputs: ["Evidence request"], fields: ["tpl-obligations.readiness"], health: [0.9, 0.92, 0.88] },
  { id: "compliance-renewals", name: "Renewal tracking", agent: "a-compliance", version: 2, trigger: "Renewal within 45 days", steps: [["Retrieve contract and certificate", "retrieval", null], ["Draft renewal note", "judgment", null]], tools: ["tool:evidence.request"], policies: [], caps: ["evidence:request"], outputs: ["Renewal note"], fields: ["tpl-renewals.items"], health: [0.94, 0.95, 0.93] },
  { id: "quality-overnight", name: "Overnight failure review", agent: "a-quality", version: 3, trigger: "Nightly at 02:00", steps: [["Read yesterday's runs", "retrieval", null], ["Classify failures", "judgment", null], ["Draft fixes as commits", "tool", "tool:graph.commit"]], tools: ["tool:graph.commit"], policies: [], caps: ["graph:draft"], outputs: ["Digest", "Commits"], fields: ["tpl-improvement.items"], health: [0.9, 0.87, 0.9] },
  { id: "librarian-freshness", name: "Freshness and conflicts", agent: "a-librarian", version: 2, trigger: "New fact candidate or nightly scan", steps: [["Compare with ground truth", "retrieval", null], ["Propose resolution", "judgment", null], ["Draft change request", "tool", "tool:graph.commit"]], tools: ["tool:graph.commit"], policies: [], caps: ["graph:draft"], outputs: ["Proposal"], fields: ["tpl-freshness.items"], health: [0.92, 0.9, 0.91] },
  { id: "sentinel-access", name: "Access review", agent: "a-sentinel", version: 2, trigger: "Denied invocation or weekly review", steps: [["Read decision log", "retrieval", null], ["Assess need", "judgment", null], ["Propose grant or revoke", "tool", "tool:graph.commit"]], tools: ["tool:graph.commit"], policies: ["access-review"], caps: ["access:review"], outputs: ["Access proposal"], fields: ["tpl-access-review.items"], health: [0.95, 0.93, 0.94] },
];

export type PolicyDef = {
  key: string;
  name: string;
  cluster: string;
  criticality: Criticality;
  versions: { version: number; statement: string; params: Record<string, string | number | boolean>; validFrom: string; validTo: string | null; recordedAt: string }[];
  ruleKind: string;
  dri: string;
};

export const POLICIES: PolicyDef[] = [
  {
    key: "refund-window",
    name: "Refund window",
    cluster: "finebase-platform",
    criticality: 3,
    ruleKind: "max_days_since_purchase",
    dri: "h-hcs",
    versions: [
      { version: 1, statement: "Refunds are accepted within 14 days of purchase.", params: { days: 14 }, validFrom: "2024-07-01T00:00:00Z", validTo: "2025-06-01T00:00:00Z", recordedAt: "2024-06-20T09:00:00Z" },
      { version: 2, statement: "Refunds are accepted within 45 days of purchase.", params: { days: 45 }, validFrom: "2025-06-01T00:00:00Z", validTo: "2026-01-01T00:00:00Z", recordedAt: "2025-05-28T09:00:00Z" },
      { version: 3, statement: "Refunds are accepted within 30 days of purchase.", params: { days: 30 }, validFrom: "2026-01-01T00:00:00Z", validTo: null, recordedAt: "2025-12-15T09:00:00Z" },
    ],
  },
  { key: "refund-auto-threshold", name: "Refund auto threshold", cluster: "finebase-platform", criticality: 3, ruleKind: "max_amount_minor", dri: "h-hcs", versions: [{ version: 2, statement: "The Refund Agent may refund up to LKR 50,000 without a human.", params: { amountMinor: 5_000_000, currency: "LKR" }, validFrom: "2026-01-01T00:00:00Z", validTo: null, recordedAt: "2025-12-15T09:00:00Z" }] },
  { key: "goodwill-credit", name: "Goodwill credit cap", cluster: "finebase-platform", criticality: 2, ruleKind: "max_amount_minor", dri: "h-hcs", versions: [{ version: 1, statement: "Goodwill credits are capped at LKR 5,000 per customer per quarter.", params: { amountMinor: 500_000 }, validFrom: "2026-03-01T00:00:00Z", validTo: null, recordedAt: "2026-02-20T09:00:00Z" }] },
  { key: "pii-masking", name: "Personal data masking", cluster: "finebase-platform", criticality: 4, ruleKind: "mask_by_default", dri: "h-sec", versions: [{ version: 2, statement: "Personal data is masked by default. Every reveal is permissioned and audited.", params: { mask: true }, validFrom: "2026-02-01T00:00:00Z", validTo: null, recordedAt: "2026-01-25T09:00:00Z" }] },
  { key: "public-reply-tone", name: "Public reply tone", cluster: "finebase-platform", criticality: 2, ruleKind: "tone_gate", dri: "h-hcs", versions: [{ version: 1, statement: "Public replies are warm, specific and never promise refunds or dates.", params: { gate: "tone" }, validFrom: "2025-09-01T00:00:00Z", validTo: null, recordedAt: "2025-08-25T09:00:00Z" }] },
  { key: "pricing-change", name: "Pricing and legal pages", cluster: "finebase-platform", criticality: 3, ruleKind: "requires_l1", dri: "h-founder", versions: [{ version: 1, statement: "Changes to pricing, checkout and legal pages need L1 approval.", params: { pages: "pricing,checkout,legal" }, validFrom: "2025-09-01T00:00:00Z", validTo: null, recordedAt: "2025-08-25T09:00:00Z" }] },
  { key: "write-off", name: "Write offs", cluster: "finance-compliance", criticality: 3, ruleKind: "requires_l1", dri: "h-fd", versions: [{ version: 1, statement: "Writing off any receivable needs the Finance Director.", params: { amountMinor: 0 }, validFrom: "2025-09-01T00:00:00Z", validTo: null, recordedAt: "2025-08-25T09:00:00Z" }] },
  { key: "data-retention", name: "Data retention", cluster: "finance-compliance", criticality: 3, ruleKind: "retention_days", dri: "h-sec", versions: [{ version: 2, statement: "Financial records are kept for 7 years (sample). Chat transcripts for 2 years.", params: { financeDays: 2555, chatDays: 730 }, validFrom: "2026-01-01T00:00:00Z", validTo: null, recordedAt: "2025-12-20T09:00:00Z" }] },
  { key: "vat-evidence", name: "VAT evidence pack (sample)", cluster: "finance-compliance", criticality: 4, ruleKind: "evidence_required", dri: "h-fd", versions: [{ version: 1, statement: "Sample: each VAT return needs the sales register, input VAT invoices and the bank statement for the period.", params: { items: 3 }, validFrom: "2026-01-01T00:00:00Z", validTo: null, recordedAt: "2025-12-20T09:00:00Z" }] },
  { key: "access-review", name: "Access review", cluster: "finebase-platform", criticality: 3, ruleKind: "periodic_review", dri: "h-sec", versions: [{ version: 1, statement: "Agent capability grants are reviewed weekly. New scopes need L1.", params: { cadence: "weekly" }, validFrom: "2025-10-01T00:00:00Z", validTo: null, recordedAt: "2025-09-25T09:00:00Z" }] },
];

export const SENSORS = [
  { id: "s-chat", name: "Chat widget", source: "finebase.lk widget", kind: "chat", cluster: "finebase-platform", events: ["message.created", "conversation.closed"], pd: true, rate: 22 },
  { id: "s-support-inbox", name: "Support inbox", source: "support@finebase.lk", kind: "inbox", cluster: "finebase-platform", events: ["email.received"], pd: true, rate: 9 },
  { id: "s-usage", name: "Product usage events", source: "Platform event bus", kind: "analytics", cluster: "finebase-platform", events: ["feature.used", "session.started"], pd: false, rate: 640 },
  { id: "s-payments", name: "Payment gateway webhooks", source: "Payment gateway", kind: "payments", cluster: "finebase-platform", events: ["charge.succeeded", "charge.failed", "refund.created"], pd: true, rate: 12 },
  { id: "s-lead-forms", name: "Lead forms", source: "finebase.lk/contact", kind: "website", cluster: "finebase-platform", events: ["form.submitted"], pd: true, rate: 1.5 },
  { id: "s-calendars", name: "Team calendars", source: "Calendar provider", kind: "calendar", cluster: "finebase-platform", events: ["event.created", "event.updated"], pd: false, rate: 4 },
  { id: "s-booking", name: "Booking page", source: "finebase.lk/book", kind: "website", cluster: "finebase-platform", events: ["slot.booked"], pd: true, rate: 0.6 },
  { id: "s-transcripts", name: "Meeting transcripts", source: "Meeting recorder", kind: "documents", cluster: "finebase-platform", events: ["transcript.ready"], pd: true, rate: 0.5 },
  { id: "s-crm", name: "CRM", source: "CRM", kind: "crm", cluster: "finebase-platform", events: ["deal.stage_changed"], pd: true, rate: 2 },
  { id: "s-contracts", name: "Contract vault", source: "Document store", kind: "documents", cluster: "finance-compliance", events: ["contract.signed", "contract.expiring"], pd: false, rate: 0.2 },
  { id: "s-tracker", name: "Project tracker", source: "Project tracker", kind: "crm", cluster: "finebase-platform", events: ["issue.updated"], pd: false, rate: 18 },
  { id: "s-repo", name: "Repository activity", source: "Git host", kind: "repository", cluster: "finebase-platform", events: ["push", "pull_request.merged"], pd: false, rate: 6 },
  { id: "s-uptime", name: "Uptime monitor", source: "Uptime monitor", kind: "monitor", cluster: "finebase-platform", events: ["monitor.down", "monitor.up"], pd: false, rate: 0.1 },
  { id: "s-errors", name: "Error tracker", source: "Error tracker", kind: "monitor", cluster: "finebase-platform", events: ["issue.created"], pd: false, rate: 3 },
  { id: "s-cms", name: "Website CMS", source: "CMS", kind: "website", cluster: "finebase-platform", events: ["page.published"], pd: false, rate: 0.3 },
  { id: "s-releases", name: "Product releases", source: "Release notes", kind: "repository", cluster: "finebase-platform", events: ["release.published"], pd: false, rate: 0.05 },
  { id: "s-clarity", name: "Microsoft Clarity", source: "Clarity project finebase.lk", kind: "clarity", cluster: "finebase-platform", events: ["rage_click", "dead_click", "scroll_depth"], pd: false, rate: 85 },
  { id: "s-analytics", name: "Website analytics", source: "Analytics", kind: "analytics", cluster: "finebase-platform", events: ["page_view", "conversion"], pd: false, rate: 210 },
  { id: "s-clicks", name: "Click sensors", source: "Tracking plan", kind: "website", cluster: "finebase-platform", events: ["pricing_toggle.clicked", "cta.clicked"], pd: false, rate: 40 },
  { id: "s-reviews", name: "Review sites", source: "Review sites", kind: "website", cluster: "finebase-platform", events: ["review.created"], pd: true, rate: 0.2 },
  { id: "s-nps", name: "NPS surveys", source: "Survey tool", kind: "website", cluster: "finebase-platform", events: ["response.created"], pd: true, rate: 0.7 },
  { id: "s-obligations", name: "Obligations calendar", source: "Compliance calendar", kind: "calendar", cluster: "finance-compliance", events: ["obligation.due"], pd: false, rate: 0.05 },
  { id: "s-accounting", name: "Accounting exports", source: "Accounting system", kind: "documents", cluster: "finance-compliance", events: ["export.ready"], pd: false, rate: 0.1 },
  { id: "s-finance-inbox", name: "Finance inbox", source: "finance@finebase.lk", kind: "inbox", cluster: "finance-compliance", events: ["email.received"], pd: true, rate: 0 },
  { id: "s-vendor-invoices", name: "Vendor invoices", source: "Accounts payable", kind: "documents", cluster: "finance-compliance", events: ["invoice.received"], pd: false, rate: 0.4 },
  { id: "s-certs", name: "Certificate monitors", source: "TLS monitor", kind: "monitor", cluster: "finance-compliance", events: ["certificate.expiring"], pd: false, rate: 0.01 },
  { id: "s-bank-feed", name: "Bank feed", source: "Bank statement import", kind: "payments", cluster: "finance-compliance", events: ["transaction.posted"], pd: true, rate: 3 },
  { id: "s-card-feed", name: "Card feed", source: "Company card", kind: "payments", cluster: "finance-compliance", events: ["transaction.posted"], pd: true, rate: 1 },
] as const;

export const TEMPLATES: { id: string; name: string; cluster: string; cadence: string; owner: string; agents: string[]; fields: [string, string, string[]][]; freshness: string; evidence: string[] }[] = [
  { id: "tpl-care-weekly", name: "Weekly care report", cluster: "finebase-platform", cadence: "Weekly, Monday 08:00", owner: "h-hcs", agents: ["a-care"], fields: [["answered", "Conversations answered", ["s-chat", "s-support-inbox"]], ["csat", "CSAT", ["s-nps"]], ["credits", "Goodwill credits", ["s-payments"]]], freshness: "Fields older than 7 days are stale", evidence: [] },
  { id: "tpl-refund-register", name: "Refund register", cluster: "finebase-platform", cadence: "Per refund", owner: "h-hcs", agents: ["a-refund"], fields: [["refunds", "Refunds issued", ["s-payments"]], ["outside", "Outside policy cases", ["s-support-inbox"]], ["value", "Value refunded", ["s-payments"]]], freshness: "Updated within 1 hour of a refund", evidence: ["Gateway refund receipt"] },
  { id: "tpl-revenue-health", name: "Revenue health", cluster: "finance-compliance", cadence: "Daily", owner: "h-fd", agents: ["a-billing"], fields: [["mrr", "MRR", ["s-payments"]], ["failed", "Failed charges", ["s-payments"]], ["recovered", "Recovered", ["s-payments"]]], freshness: "Daily by 07:00", evidence: [] },
  { id: "tpl-pipeline", name: "Pipeline report", cluster: "finebase-platform", cadence: "Weekly", owner: "h-founder", agents: ["a-sales"], fields: [["qualified", "Qualified leads", ["s-lead-forms", "s-crm"]], ["quotes", "Quotes sent", ["s-crm"]], ["won", "Deals won", ["s-crm"]]], freshness: "Weekly", evidence: [] },
  { id: "tpl-meeting-log", name: "Meeting log", cluster: "finebase-platform", cadence: "Per meeting", owner: "h-founder", agents: ["a-scheduler"], fields: [["booked", "Meetings booked", ["s-calendars"]], ["noshow", "No shows", ["s-calendars"]]], freshness: "Same day", evidence: [] },
  { id: "tpl-action-log", name: "Action log", cluster: "finebase-platform", cadence: "Per meeting", owner: "h-founder", agents: ["a-scheduler"], fields: [["actions", "Action items", ["s-transcripts"]], ["owners", "Owners assigned", ["s-transcripts"]]], freshness: "Within 2 hours", evidence: [] },
  { id: "tpl-onboarding", name: "Onboarding checklist", cluster: "finebase-platform", cadence: "Per client", owner: "h-hcs", agents: ["a-onboarding"], fields: [["items", "Checklist items", ["s-contracts"]], ["access", "Access granted", ["s-crm"]]], freshness: "Daily", evidence: ["Signed contract"] },
  { id: "tpl-client-status", name: "Client status report", cluster: "finebase-platform", cadence: "Weekly, Friday", owner: "h-founder", agents: ["a-delivery"], fields: [["report", "Report sent", ["s-tracker"]], ["sla", "SLA met", ["s-uptime"]], ["incidents", "Incidents", ["s-uptime"]]], freshness: "Weekly", evidence: [] },
  { id: "tpl-content-log", name: "Content change log", cluster: "finebase-platform", cadence: "Per change", owner: "h-hcs", agents: ["a-web"], fields: [["changes", "Pages changed", ["s-cms"]], ["notes", "Release notes", ["s-releases"]]], freshness: "Per change", evidence: [] },
  { id: "tpl-experiments", name: "Experiment report", cluster: "finebase-platform", cadence: "Per experiment", owner: "h-hcs", agents: ["a-insights"], fields: [["proposed", "Experiments proposed", ["s-clarity"]], ["running", "Running", ["s-analytics"]], ["learnings", "Learnings recorded", ["s-analytics"]]], freshness: "Weekly", evidence: [] },
  { id: "tpl-voc", name: "Voice of customer report", cluster: "finebase-platform", cadence: "Monthly", owner: "h-hcs", agents: ["a-reputation"], fields: [["replies", "Public replies", ["s-reviews"]], ["nps", "NPS", ["s-nps"]]], freshness: "Monthly", evidence: [] },
  { id: "tpl-incident", name: "Incident report", cluster: "finebase-platform", cadence: "Per incident", owner: "h-founder", agents: ["a-incident"], fields: [["statement", "Public statement", ["s-uptime"]], ["rca", "Root cause", ["s-errors"]]], freshness: "Within 48 hours", evidence: [] },
  { id: "tpl-obligations", name: "Obligation readiness", cluster: "finance-compliance", cadence: "Daily", owner: "h-fd", agents: ["a-compliance"], fields: [["readiness", "Readiness per obligation", ["s-obligations"]], ["missing", "Missing evidence", ["s-accounting"]]], freshness: "Daily", evidence: ["Evidence per obligation"] },
  { id: "tpl-renewals", name: "Renewal register", cluster: "finance-compliance", cadence: "Weekly", owner: "h-fd", agents: ["a-compliance"], fields: [["items", "Renewals in 45 days", ["s-contracts", "s-certs"]]], freshness: "Weekly", evidence: [] },
  { id: "tpl-receivables", name: "Receivables aging", cluster: "finance-compliance", cadence: "Weekly", owner: "h-fd", agents: ["a-billing"], fields: [["aging", "Aging buckets", ["s-bank-feed"]], ["disputes", "Disputes", ["s-finance-inbox"]]], freshness: "Weekly", evidence: [] },
  { id: "tpl-expense-log", name: "Expense log", cluster: "finance-compliance", cadence: "Per receipt", owner: "h-fd", agents: ["a-billing"], fields: [["rows", "Expenses logged", ["s-card-feed"]]], freshness: "Within 1 day", evidence: ["Receipt"] },
  { id: "tpl-data-requests", name: "Data request register", cluster: "finebase-platform", cadence: "Per request", owner: "h-sec", agents: ["a-care", "a-sentinel"], fields: [["requests", "Requests", ["s-support-inbox"]], ["deletions", "Deletions completed", ["s-support-inbox"]]], freshness: "Per request", evidence: ["Identity check"] },
  { id: "tpl-access-review", name: "Access review", cluster: "finebase-platform", cadence: "Weekly", owner: "h-sec", agents: ["a-sentinel"], fields: [["items", "Grants reviewed", []], ["denials", "Denials", []]], freshness: "Weekly", evidence: [] },
  { id: "tpl-freshness", name: "Freshness report", cluster: "finebase-platform", cadence: "Daily", owner: "h-ks", agents: ["a-librarian"], fields: [["items", "Stale or conflicting facts", []]], freshness: "Daily", evidence: [] },
  { id: "tpl-improvement", name: "Improvement digest", cluster: "finebase-platform", cadence: "Nightly", owner: "h-aiops", agents: ["a-quality"], fields: [["items", "Fixes and drafts", []]], freshness: "Nightly", evidence: [] },
];

export const ACTIVITIES: ActivityDef[] = [
  { cluster: "finebase-platform", activity: "Customer care chat and email", agent: "a-care", sensors: ["s-chat", "s-support-inbox", "s-usage"], template: "tpl-care-weekly", criticality: "C0 answers, C2 goodwill credits" },
  { cluster: "finebase-platform", activity: "Refund and cancellation requests", agent: "a-refund", sensors: ["s-support-inbox", "s-payments"], template: "tpl-refund-register", criticality: "C2 inside policy, C3 outside policy or above threshold" },
  { cluster: "finebase-platform", activity: "Subscription billing and failed payment recovery", agent: "a-billing", sensors: ["s-payments"], template: "tpl-revenue-health", criticality: "C1 reminders, C3 write offs" },
  { cluster: "finebase-platform", activity: "Quotes and proposals for service projects", agent: "a-sales", sensors: ["s-lead-forms", "s-support-inbox"], template: "tpl-pipeline", criticality: "C3 outside the rate card" },
  { cluster: "finebase-platform", activity: "Lead qualification and follow up", agent: "a-sales", sensors: ["s-lead-forms", "s-chat"], template: "tpl-pipeline", criticality: "C1" },
  { cluster: "finebase-platform", activity: "Meeting arrangement", agent: "a-scheduler", sensors: ["s-calendars", "s-booking"], template: "tpl-meeting-log", criticality: "C1" },
  { cluster: "finebase-platform", activity: "Meeting notes to action items", agent: "a-scheduler", sensors: ["s-transcripts"], template: "tpl-action-log", criticality: "C1" },
  { cluster: "finebase-platform", activity: "Client onboarding for service projects", agent: "a-onboarding", sensors: ["s-contracts", "s-crm"], template: "tpl-onboarding", criticality: "C2 access grants" },
  { cluster: "finebase-platform", activity: "Retainer SLA tracking and client status reports", agent: "a-delivery", sensors: ["s-tracker", "s-repo", "s-uptime"], template: "tpl-client-status", criticality: "C2 client facing" },
  { cluster: "finebase-platform", activity: "Website content and release notes", agent: "a-web", sensors: ["s-cms", "s-releases"], template: "tpl-content-log", criticality: "C2 general pages, C3 pricing and legal pages" },
  { cluster: "finebase-platform", activity: "UX improvement experiments", agent: "a-insights", sensors: ["s-clarity", "s-clicks", "s-analytics"], template: "tpl-experiments", criticality: "C2 to propose, C3 to ship on pricing or checkout" },
  { cluster: "finebase-platform", activity: "Reviews, NPS and public feedback replies", agent: "a-reputation", sensors: ["s-reviews", "s-nps"], template: "tpl-voc", criticality: "C2 public replies" },
  { cluster: "finebase-platform", activity: "Outage communication", agent: "a-incident", sensors: ["s-uptime", "s-errors"], template: "tpl-incident", criticality: "C3 public statements" },
  { cluster: "finance-compliance", activity: "Tax and statutory obligation readiness", agent: "a-compliance", sensors: ["s-obligations", "s-accounting", "s-finance-inbox"], template: "tpl-obligations", criticality: "C4, the system prepares, humans file" },
  { cluster: "finance-compliance", activity: "Renewals for contracts, vendor subscriptions, domains and SSL", agent: "a-compliance", sensors: ["s-contracts", "s-vendor-invoices", "s-certs"], template: "tpl-renewals", criticality: "C3" },
  { cluster: "finance-compliance", activity: "Receivables chasing for service invoices", agent: "a-billing", sensors: ["s-bank-feed"], template: "tpl-receivables", criticality: "C1 reminders, C3 disputes" },
  { cluster: "finance-compliance", activity: "Expense and receipt capture", agent: "a-billing", sensors: ["s-finance-inbox", "s-card-feed"], template: "tpl-expense-log", criticality: "C1" },
  { cluster: "finebase-platform", activity: "Personal data requests for access or deletion", agent: "a-care", sensors: ["s-support-inbox"], template: "tpl-data-requests", criticality: "C4 deletion" },
  { cluster: "finebase-platform", activity: "Access reviews", agent: "a-sentinel", sensors: [], template: "tpl-access-review", criticality: "C3 changes" },
  { cluster: "finebase-platform", activity: "Knowledge freshness and conflicts", agent: "a-librarian", sensors: [], template: "tpl-freshness", criticality: "C3 ground truth changes" },
  { cluster: "finebase-platform", activity: "Overnight failure review and fix drafting", agent: "a-quality", sensors: [], template: "tpl-improvement", criticality: "Inherits each change's criticality" },
];

export const RUN_SUBJECTS: Record<string, string[]> = {
  "a-care": ["Chat · how to export invoices", "Chat · reset two factor login", "Email · plan comparison", "Chat · API rate limits", "Email · team seats", "Chat · invoice address change"],
  "a-refund": ["Refund request · monthly plan", "Cancellation · annual plan", "Refund request · duplicate charge"],
  "a-billing": ["Failed charge · card expired", "Receivable · invoice overdue", "Receipt · cloud hosting", "Failed charge · insufficient funds"],
  "a-sales": ["Lead · logistics company", "Quote · mobile app MVP", "Lead · retail chain", "Follow up · discovery call"],
  "a-scheduler": ["Demo booking", "Sprint review scheduling", "Discovery call", "Notes · weekly sync"],
  "a-onboarding": ["Onboarding · new retainer client", "Onboarding · access checklist"],
  "a-delivery": ["Status report · retainer client", "SLA check · uptime"],
  "a-web": ["Release notes · v4.12", "Page update · careers", "Page update · case study"],
  "a-insights": ["Friction scan · pricing page", "Friction scan · signup"],
  "a-reputation": ["Review reply · 4 stars", "NPS follow up"],
  "a-incident": ["Status draft · API latency"],
  "a-compliance": ["Readiness check · EPF", "Renewal · SSL certificate", "Readiness check · APIT"],
  "a-quality": ["Overnight review"],
  "a-librarian": ["Freshness scan"],
  "a-sentinel": ["Access review"],
};
