import type {
  AccessDecision,
  Agent,
  AuditEvent,
  Branch,
  Commit,
  Conversation,
  Document,
  Experiment,
  Fact,
  GraphEdge,
  GraphNode,
  Human,
  LibrarianItem,
  Loop,
  Obligation,
  Policy,
  Run,
  RunStatus,
  Sensitivity,
  Sensor,
  Skill,
  Template,
  TraceStep,
} from "@/contracts";
import { readinessOf, statusOf } from "@/lib/governance/readiness";
import { DAY, HOUR, Rng, SEED_NOW, hashString, iso } from "../prng";
import type { TenantData } from "../types";
import { runOvernightReview } from "../ops";
import { emptyStudio, seedStudio } from "../studio/seed";
import { seedTrends } from "./trends";
import { seedMemory } from "./memory";
import { ACTIVITIES, AGENTS, CLUSTERS, HUMANS, POLICIES, RUN_SUBJECTS, SENSORS, SKILLS, TEMPLATES, TOOLS } from "./catalog";

const at = (days: number, hours = 0) => iso(SEED_NOW + days * DAY + hours * HOUR);
const FAILURE_CLASSES = ["wrong route", "missing knowledge", "stale policy", "tool error", "quality gate"];

const THRESHOLDS = {
  refundAutoLimitMinor: 5_000_000,
  writeOffLimitMinor: 0,
  goodwillCreditLimitMinor: 500_000,
  l2ApprovalCeiling: 2 as const,
  coolingPeriodHoursC4: 4,
  approvalExpiryHours: 72,
};

function emptyData(): Omit<TenantData, "tenant"> {
  return {
    clusters: [], humans: [], agents: [], activities: [], skills: [], policies: [], facts: [], documents: [], filingRules: [],
    accessRules: [], sensors: [], trackingPlan: [], templates: [], resolver: [], graph: { nodes: [], edges: [] }, librarian: [],
    runs: [], specialSteps: {}, conversations: [], accessDecisions: [], branches: [], commits: [], changeRequests: [], approvals: [],
    obligations: [], evidenceRequests: [], grants: [], risks: [], readinessRules: [], gaps: [], loops: [], experiments: [], audit: [],
    notifications: [], digest: null, trends: [], memory: { traces: [], patterns: [], drifts: [], skills: [] }, studio: emptyStudio(), counter: 0,
  };
}

// ---------------------------------------------------------------- Finebase Labs

export function buildFinebase(): TenantData {
  const rng = new Rng("finebase-labs-seed-1");
  const tenantId = "demo-fbl";
  const d: TenantData = {
    tenant: {
      id: tenantId,
      name: "demo-fbl",
      currency: "LKR",
      timezone: "Asia/Colombo",
      locale: "en-LK",
      brand: { primary: "#4f46e5", mark: "FB" },
      clusters: CLUSTERS.map((c) => c.id),
      criticalityThresholds: THRESHOLDS,
      isScaleDemo: false,
    },
    ...emptyData(),
  };

  d.humans = HUMANS.map(
    (h): Human => ({
      id: h.id, tenantId, name: h.name, title: h.title, tier: h.tier, roles: [...h.roles],
      attributes: { clearance: h.clearance, department: h.roles[0] }, driOf: [...h.driOf],
      maxApprovalCriticality: h.max as 0 | 2 | 4, color: h.color,
    }),
  );

  d.activities = ACTIVITIES;

  d.clusters = CLUSTERS.map((c, i) => ({
    id: c.id, tenantId, name: c.name, description: c.description, status: c.status,
    connectors: SENSORS.filter((s) => s.cluster === c.id).map((s) => s.name), dri: c.dri,
    health: c.status === "active" ? [91, 84][i] ?? 0 : 0,
    autonomyRate: c.status === "active" ? [0.81, 0.69][i] ?? 0 : 0,
    escalationRate: c.status === "active" ? [0.06, 0.09][i] ?? 0 : 0,
    moneyAtStakeMinor: c.status === "active" ? [1_240_000_00, 3_870_000_00][i] ?? 0 : 0,
    openRisks: c.status === "active" ? [2, 3][i] ?? 0 : 0,
    costPerTaskUsd: c.status === "active" ? [0.05, 0.08][i] ?? 0 : 0,
  }));

  // Skills
  d.skills = SKILLS.map((s): Skill => {
    const agent = AGENTS.find((a) => a.id === s.agent)!;
    return {
      id: s.id, tenantId, name: s.name, version: s.version, branch: "main", status: "active", clusterId: agent.cluster, trigger: s.trigger,
      inputs: agent.sensors.map((x) => SENSORS.find((y) => y.id === x)?.name ?? x),
      steps: s.steps.map(([text, kind, tool], i) => ({ id: `${s.id}-st${i + 1}`, kind, text, tool })),
      tools: s.tools, policies: s.policies, requiredCapabilities: s.caps, outputs: s.outputs, templateFields: s.fields,
      evalSuite: { id: `eval-${s.id}`, cases: 24 + (hashString(s.id) % 40), passRate: s.health[0] },
      health: { taskSuccess: s.health[0], consistencyPassK: s.health[1], k: 8, conformance: s.health[2] },
      agentIds: [s.agent], dri: agent.dri, updatedAt: at(-(hashString(s.id) % 40) - 2), origin: "authored",
    };
  });

  // Agents
  d.agents = AGENTS.map((a, i): Agent => {
    const working = a.kind === "worker" && i % 3 !== 2;
    return {
      id: a.id, tenantId, name: a.name, kind: a.kind, tier: a.kind === "worker" ? "L3" : "L2", clusterId: a.cluster, description: a.description,
      autonomy: a.autonomy,
      skills: SKILLS.filter((s) => s.agent === a.id).map((s) => ({ id: s.id, version: s.version, branch: "main" })),
      capabilities: a.capabilities, accessLevel: a.level, sensors: a.sensors, templates: a.templates,
      policies: [...new Set(SKILLS.filter((s) => s.agent === a.id).flatMap((s) => s.policies))],
      status: a.id === "a-incident" ? "idle" : working ? "working" : "idle",
      workKind: working ? (["retrieval", "judgment", "tool"] as const)[i % 3] : null,
      dri: a.dri, queueDepth: working ? rng.int(1, 9) : 0, throughputPerHour: a.throughput,
      errorRate: Math.round(rng.float() * 60) / 1000, costTodayUsd: Math.round(a.throughput * 24 * rng.float() * 18) / 100,
      taskSuccess: 0.8 + rng.float() * 0.17,
      training: [
        { at: at(-120 - i), event: "Enrolled as trainee", by: a.dri },
        { at: at(-80 - i), event: "Passed eval suite, promoted to supervised", by: a.dri },
        ...(a.autonomy === "autonomous" ? [{ at: at(-30 - i), event: "Promoted to autonomous after 30 days above 90% task success", by: "h-founder" }] : []),
      ],
    };
  });

  // Policies with full version history
  for (const p of POLICIES) {
    p.versions.forEach((v, i) => {
      const next = p.versions[i + 1];
      d.policies.push({
        id: `${p.key}@v${v.version}`, key: p.key, tenantId, name: p.name, version: v.version, branch: "main", clusterId: p.cluster,
        statement: v.statement, rule: { kind: p.ruleKind, params: v.params }, criticality: p.criticality,
        validFrom: v.validFrom, validTo: v.validTo, recordedAt: v.recordedAt, supersededBy: next ? `${p.key}@v${next.version}` : null,
        evidence: p.key === "refund-window" ? ["doc-refund-policy"] : [],
        freshness:
          p.key === "refund-window" && !next
            ? { intervalClosed: false, driftPointAt: at(-12), conformance: 0.62, conflictingEvidence: 1, outdatedRelianceRate: 0.18 }
            : { intervalClosed: !!v.validTo, driftPointAt: null, conformance: 0.9 + (hashString(p.key) % 9) / 100, conflictingEvidence: 0, outdatedRelianceRate: 0.01 },
        dependents: ([] as Policy["dependents"]).concat(SKILLS.filter((s) => s.policies.includes(p.key)).map((s) => ({ type: "skill" as const, id: s.id, label: s.name })),
          p.key === "refund-window" ? [{ type: "template" as const, id: "tpl-refund-register", label: "Refund register" }, { type: "web_page" as const, id: "web:/pricing#refunds", label: "Pricing page, refund section" }] : []),
        dri: p.dri,
      });
    });
  }

  // Documents and facts
  const doc = (id: string, title: string, cluster: string, type: string, sensitivity: Sensitivity, by: string, daysAgo: number, pd = false, retention = 2555, rule = "finance-records"): Document => ({
    id, tenantId, clusterId: cluster, title, source: type === "contract" ? "Contract vault" : type === "email" ? "Finance inbox" : "Upload", type, sensitivity,
    extractionStatus: "done", linkedFacts: [], retentionDays: retention, filingRule: rule, uploadedBy: by, uploadedAt: at(-daysAgo), sizeKb: 80 + (hashString(id) % 900), personalData: pd,
  });
  d.documents = [
    doc("doc-refund-policy", "Refund policy 2026.pdf", "finebase-platform", "policy", "internal", "h-hcs", 300, false, 3650, "policies"),
    doc("doc-pricing-oct-2026", "Pricing sheet October 2026.pdf", "finebase-platform", "pricing", "internal", "h-founder", 3, false, 3650, "policies"),
    doc("doc-sales-register-sep", "Sales register September 2026 (sample).xlsx", "finance-compliance", "ledger", "confidential", "h-fd", 6),
    doc("doc-vat-cert", "VAT registration certificate (sample).pdf", "finance-compliance", "certificate", "restricted", "h-fd", 400),
    doc("doc-ssl-old", "TLS monitor export, August.csv", "finance-compliance", "monitor", "internal", "h-sec", 60, false, 365, "monitoring"),
    doc("doc-domain-invoice", "Domain renewal invoice finebase.lk.pdf", "finance-compliance", "invoice", "internal", "h-fd", 12),
    doc("doc-epf-schedule-sep", "EPF contribution schedule September (sample).pdf", "finance-compliance", "schedule", "restricted", "h-fd", 4),
    doc("doc-apit-sep", "APIT computation September (sample).xlsx", "finance-compliance", "ledger", "restricted", "h-fd", 5),
    doc("doc-payroll-sep", "Payroll summary September (sample).pdf", "finance-compliance", "ledger", "restricted", "h-fd", 5, true),
    doc("doc-msa-lanka-logistics", "MSA Lanka Logistics retainer.pdf", "finance-compliance", "contract", "confidential", "h-founder", 320),
    doc("doc-rate-card", "Service rate card 2026 (sample).pdf", "finebase-platform", "pricing", "confidential", "h-founder", 200, false, 3650, "policies"),
    doc("doc-incident-rca", "Incident RCA 2 October.md", "finebase-platform", "report", "internal", "h-aiops", 5, false, 730, "operations"),
    doc("doc-support-handbook", "Support handbook v5.md", "finebase-platform", "handbook", "internal", "h-hcs", 90, false, 1825, "policies"),
    doc("doc-nps-q3", "NPS Q3 2026 export.csv", "finebase-platform", "export", "internal", "h-hcs", 8, true, 730, "operations"),
    doc("doc-privacy-notice", "Privacy notice.pdf", "finebase-platform", "legal", "public", "h-sec", 250, false, 3650, "policies"),
    doc("doc-terms", "Terms of service.pdf", "finebase-platform", "legal", "public", "h-founder", 250, false, 3650, "policies"),
    doc("doc-release-412", "Release notes v4.12.md", "finebase-platform", "release", "public", "h-aiops", 9, false, 730, "operations"),
    doc("doc-bank-aug", "Bank statement August 2026 (sample).pdf", "finance-compliance", "statement", "restricted", "h-fd", 30, true),
    doc("doc-cloud-invoice-sep", "Cloud hosting invoice September.pdf", "finance-compliance", "invoice", "internal", "h-fd", 7),
    doc("doc-shareholders", "Shareholder register (sample).pdf", "finance-compliance", "register", "restricted", "h-founder", 180, true),
    doc("doc-old-deck", "Investor deck 2024.pptx", "finebase-platform", "presentation", "confidential", "h-founder", 600, false, 1825, "general"),
    doc("doc-customer-1042", "Order receipt CUS-1042.pdf", "finebase-platform", "receipt", "confidential", "a-refund", 41, true, 2555, "finance-records"),
  ];

  const fact = (id: string, statement: string, subject: string, value: string, validFrom: string, docId: string, quote: string, opts: Partial<Fact> = {}): Fact => ({
    id, tenantId, clusterId: d.documents.find((x) => x.id === docId)?.clusterId ?? "finebase-platform", statement, subject, value, validFrom, validTo: null,
    recordedAt: opts.recordedAt ?? at(-(hashString(id) % 60) - 1), evidence: [{ documentId: docId, page: 1 + (hashString(id) % 4), quote }],
    verifiedBy: "h-ks", status: "verified", sensitivity: "internal", dependents: [], ...opts,
  });
  d.facts = [
    fact("f-refund-window", "Refunds are accepted within 30 days of purchase", "refund policy", "30 days", "2026-01-01T00:00:00Z", "doc-refund-policy", "We accept refund requests within 30 days of the purchase date.", {
      dependents: [{ type: "skill", id: "refund-standard", label: "Refund inside policy" }, { type: "template", id: "tpl-refund-register", label: "Refund register" }, { type: "web_page", id: "web:/pricing#refunds", label: "Pricing page, refund section" }, { type: "policy", id: "refund-window@v3", label: "Refund window v3" }],
    }),
    fact("f-pricing-oct-refund", "Annual plans have a 14 day refund window from 1 November 2026", "refund policy", "14 days", "2026-11-01T00:00:00Z", "doc-pricing-oct-2026", "Annual plans purchased from 1 November 2026 can be refunded within 14 days.", { status: "conflicted", verifiedBy: null, recordedAt: at(-3) }),
    fact("f-refund-threshold", "The Refund Agent may refund up to LKR 50,000 without a human", "refund threshold", "LKR 50,000", "2026-01-01T00:00:00Z", "doc-refund-policy", "Refunds above LKR 50,000 need a human decision."),
    fact("f-annual-price", "Annual Growth plan costs LKR 240,000 (sample)", "pricing", "LKR 240,000", "2026-01-01T00:00:00Z", "doc-pricing-oct-2026", "Growth, billed annually: LKR 240,000."),
    fact("f-monthly-price", "Monthly Growth plan costs LKR 24,000 (sample)", "pricing", "LKR 24,000", "2026-01-01T00:00:00Z", "doc-pricing-oct-2026", "Growth, billed monthly: LKR 24,000."),
    fact("f-rate-card", "Service projects bill LKR 9,500 per engineer hour (sample)", "rate card", "LKR 9,500", "2026-01-01T00:00:00Z", "doc-rate-card", "Standard engineer hour: LKR 9,500.", { sensitivity: "confidential" }),
    fact("f-sla", "Retainer clients get a first response within 4 business hours", "SLA", "4 business hours", "2025-10-01T00:00:00Z", "doc-msa-lanka-logistics", "First response within four (4) business hours.", { sensitivity: "confidential" }),
    fact("f-vat-reg", "Finebase Labs VAT registration is on file (sample number)", "VAT registration", "on file", "2024-04-01T00:00:00Z", "doc-vat-cert", "Registration certificate issued to Finebase Labs (Pvt) Ltd.", { sensitivity: "restricted" }),
    fact("f-vat-reg-dup", "VAT registration certificate exists for Finebase Labs", "VAT registration", "on file", "2024-04-01T00:00:00Z", "doc-vat-cert", "Certificate of registration.", { sensitivity: "restricted", verifiedBy: null, status: "unverified" }),
    fact("f-ssl-expiry", "TLS certificate for app.finebase.lk expires on 2 October 2026", "TLS certificate", "2026-10-02", "2025-10-02T00:00:00Z", "doc-ssl-old", "app.finebase.lk notAfter 2026-10-02", { status: "stale" }),
    fact("f-domain", "finebase.lk renews on 7 November 2026", "domain", "2026-11-07", "2025-11-07T00:00:00Z", "doc-domain-invoice", "Renewal period ends 07/11/2026."),
    fact("f-sales-register-sep", "September 2026 sales register is complete (sample)", "VAT September", "complete", "2026-10-01T00:00:00Z", "doc-sales-register-sep", "Total taxable supplies for September.", { sensitivity: "confidential" }),
    fact("f-apit-sep", "APIT for September 2026 is computed (sample)", "APIT September", "computed", "2026-10-01T00:00:00Z", "doc-apit-sep", "APIT payable for September.", { sensitivity: "restricted" }),
    fact("f-payroll-sep", "September 2026 payroll summary is approved (sample)", "payroll September", "approved", "2026-10-01T00:00:00Z", "doc-payroll-sep", "Approved by Finance Director.", { sensitivity: "restricted" }),
    fact("f-epf-schedule", "EPF contribution schedule for September is prepared (sample)", "EPF September", "prepared", "2026-10-01T00:00:00Z", "doc-epf-schedule-sep", "Employer 12%, employee 8% (sample).", { sensitivity: "restricted" }),
    fact("f-retainer-renewal", "Lanka Logistics retainer renews on 30 November 2026", "retainer", "2026-11-30", "2025-12-01T00:00:00Z", "doc-msa-lanka-logistics", "Term renews automatically on 30 November.", { sensitivity: "confidential" }),
    fact("f-cloud", "Cloud hosting subscription renews monthly on the 3rd", "cloud hosting", "monthly", "2026-01-03T00:00:00Z", "doc-cloud-invoice-sep", "Billing period renews on the 3rd."),
    fact("f-goodwill-cap", "Goodwill credits are capped at LKR 5,000 per quarter", "goodwill credit", "LKR 5,000", "2026-03-01T00:00:00Z", "doc-support-handbook", "Credits up to LKR 5,000 per customer per quarter."),
    fact("f-support-hours", "Support hours are 08:00 to 20:00 Asia/Colombo", "support hours", "08:00 to 20:00", "2025-06-01T00:00:00Z", "doc-support-handbook", "We answer between 8 am and 8 pm, Sri Lanka time."),
    fact("f-chat-retention", "Chat transcripts are kept for 2 years", "retention", "2 years", "2026-01-01T00:00:00Z", "doc-privacy-notice", "Chat transcripts are retained for two years."),
    fact("f-incident", "The 2 October API latency incident was caused by cache eviction", "incident", "cache eviction", "2026-10-02T00:00:00Z", "doc-incident-rca", "Root cause: aggressive cache eviction after deploy."),
    fact("f-nps-q3", "NPS for Q3 2026 is 46 (sample)", "NPS", "46", "2026-10-01T00:00:00Z", "doc-nps-q3", "Q3 NPS: 46."),
    fact("f-release-412", "Release 4.12 adds invoice export to CSV", "release", "4.12", "2026-09-29T00:00:00Z", "doc-release-412", "New: export invoices as CSV."),
    fact("f-pricing-toggle", "The pricing page toggle defaults to monthly billing", "pricing page", "monthly default", "2026-04-01T00:00:00Z", "doc-pricing-oct-2026", "Toggle: Monthly | Annual (save 17%)."),
    fact("f-cus-1042", "CUS-1042 bought the annual Growth plan on 28 August 2026 for LKR 85,000", "CUS-1042", "LKR 85,000", "2026-08-28T00:00:00Z", "doc-customer-1042", "Annual Growth, discounted, LKR 85,000.", { sensitivity: "confidential", verifiedBy: "a-refund" }),
    fact("f-shareholders", "Shareholder register is current (sample)", "shareholders", "current", "2026-04-01T00:00:00Z", "doc-shareholders", "Register of members as at 31 March.", { sensitivity: "restricted" }),
    fact("f-cloud-budget", "Cloud hosting budget for FY 2026/27 is approved (sample)", "cloud budget", "approved", "2026-04-01T00:00:00Z", "doc-cloud-invoice-sep", "Budget line approved."),
  ];
  for (const f of d.facts) for (const e of f.evidence) d.documents.find((x) => x.id === e.documentId)?.linkedFacts.push(f.id);

  d.filingRules = [
    { id: "policies", match: "Policies, pricing, legal", clusterId: "finebase-platform", type: "policy", sensitivity: "internal", retentionDays: 3650 },
    { id: "finance-records", match: "Ledgers, statements, invoices, receipts", clusterId: "finance-compliance", type: "ledger", sensitivity: "confidential", retentionDays: 2555 },
    { id: "monitoring", match: "Monitor exports", clusterId: "finance-compliance", type: "monitor", sensitivity: "internal", retentionDays: 365 },
    { id: "operations", match: "Reports, releases, exports", clusterId: "finebase-platform", type: "report", sensitivity: "internal", retentionDays: 730 },
    { id: "general", match: "Anything else", clusterId: "finebase-platform", type: "general", sensitivity: "internal", retentionDays: 1825 },
  ];

  d.accessRules = [
    { id: "sr-refund-tool", tenantId, name: "Refund tool needs refund capability", appliesTo: "tool:billing.refund", requiresRoles: [], requiresAttributes: {}, requiresCapability: "refund:issue", sensitivity: "confidential", description: "Only agents holding refund:issue may call billing.refund. Amount ceilings come from refund-auto-threshold." },
    { id: "sr-credit-tool", tenantId, name: "Credit tool needs goodwill capability", appliesTo: "tool:billing.credit", requiresRoles: [], requiresAttributes: {}, requiresCapability: "credit:goodwill", sensitivity: "confidential", description: "Goodwill credits are capped by policy goodwill-credit." },
    { id: "sr-finance-restricted", tenantId, name: "Finance records are restricted", appliesTo: "document:finance-records", requiresRoles: ["finance"], requiresAttributes: { clearance: "restricted" }, requiresCapability: null, sensitivity: "restricted", description: "Tax, payroll and bank records need restricted clearance." },
    { id: "sr-finance-inbox", tenantId, name: "Finance inbox needs a granted scope", appliesTo: "tool:finance-inbox.read", requiresRoles: [], requiresAttributes: {}, requiresCapability: "finance:read", sensitivity: "restricted", description: "No agent reads the finance inbox until an L1 grant exists." },
    { id: "sr-pii", tenantId, name: "Personal data masked by default", appliesTo: "fact:personal", requiresRoles: [], requiresAttributes: { clearance: "confidential" }, requiresCapability: null, sensitivity: "confidential", description: "Personal data is masked. Reveal is permissioned and audited." },
    { id: "sr-pricing-pages", tenantId, name: "Pricing pages need L1", appliesTo: "tool:cms.publish#pricing", requiresRoles: ["dri"], requiresAttributes: {}, requiresCapability: "cms:publish", sensitivity: "internal", description: "Pricing, checkout and legal pages move only with an L1 approval." },
    { id: "sr-graph-write", tenantId, name: "Graph writes are drafts", appliesTo: "tool:graph.commit", requiresRoles: [], requiresAttributes: {}, requiresCapability: "graph:draft", sensitivity: "confidential", description: "Agents commit to sandbox branches only. Main moves through change requests." },
    { id: "sr-public-reply", tenantId, name: "Public replies need reply capability", appliesTo: "tool:inbox.reply", requiresRoles: [], requiresAttributes: {}, requiresCapability: "reply:customer", sensitivity: "internal", description: "Customer facing replies pass the tone gate." },
  ];

  d.sensors = SENSORS.map((s): Sensor => ({
    id: s.id, tenantId, clusterId: s.cluster, name: s.name, source: s.source, kind: s.kind, events: [...s.events],
    subscribers: AGENTS.filter((a) => (a.sensors as string[]).includes(s.id)).map((a) => a.id),
    health: s.id === "s-finance-inbox" ? "down" : s.id === "s-certs" ? "degraded" : "ok",
    scopes: s.id === "s-finance-inbox" ? ["not granted"] : [`read:${s.kind}`], retentionDays: s.pd ? 730 : 365, personalData: s.pd,
    lastEventAt: at(0, -(hashString(s.id) % 50) / 10), eventsPerHour: s.rate,
  }));

  d.trackingPlan = [
    { id: "tp-1", selector: "[data-track=pricing-toggle]", elementLabel: "Pricing toggle (Monthly | Annual)", eventName: "pricing_toggle.clicked", properties: ["from", "to", "plan"], privacy: { personalData: false, maskText: false }, subscribers: ["a-insights", "loop-website"], createdBy: "h-aiops", createdAt: at(-40) },
    { id: "tp-2", selector: "[data-track=hero-cta]", elementLabel: "Hero call to action", eventName: "cta.clicked", properties: ["label", "page"], privacy: { personalData: false, maskText: false }, subscribers: ["a-insights"], createdBy: "h-aiops", createdAt: at(-40) },
  ];

  const now = SEED_NOW;
  d.templates = TEMPLATES.map((t, i): Template => {
    const stale = t.id === "tpl-voc" || t.id === "tpl-receivables";
    const partial = t.id === "tpl-obligations" || t.id === "tpl-experiments" || t.id === "tpl-onboarding";
    return {
      id: t.id, tenantId, clusterId: t.cluster, name: t.name, cadence: t.cadence, owner: t.owner, assignedAgents: t.agents, freshnessRule: t.freshness, requiredEvidence: t.evidence,
      status: stale ? "stale" : partial ? "partial" : "complete",
      fields: t.fields.map(([key, label, sensors], j) => {
        const empty = partial && j === t.fields.length - 1;
        const filledAt = stale ? now - (10 + j) * DAY : now - ((i + j) % 20) * HOUR;
        return {
          key, label, sensors, required: j === 0, freshnessHours: stale ? 168 : 24,
          value: empty ? null : String(10 + ((hashString(t.id + key) % 900) / 10).toFixed(0)),
          filledAt: empty ? null : iso(filledAt), filledBy: empty ? null : t.agents[0], source: empty ? null : sensors[0] ?? "graph",
        };
      }),
    };
  });

  d.resolver = d.skills.map((s, i) => ({
    id: `rr-${s.id}`, tenantId, event: s.trigger, match: s.name.toLowerCase(), skill: { id: s.id, version: s.version, branch: "main" }, agentId: s.agentIds[0], priority: 10 + i,
    triggerEval: { cases: 20 + (hashString(s.id) % 30), passRate: s.id === "refund-standard" ? 0.88 : 0.9 + (hashString(s.id) % 10) / 100, lastRunAt: at(-1, -6) },
  }));

  buildGraph(d, rng);

  d.librarian = [
    {
      id: "lib-refund-window", kind: "conflict", title: "Refund window conflicts with the October pricing sheet",
      detail: "Policy refund-window v3 says 30 days. The October 2026 pricing sheet, uploaded 3 days ago by the founder, says 14 days for annual plans from 1 November. Observed refund handling has matched the documented policy less well since 12 days ago (conformance 62%).",
      factIds: ["f-refund-window", "f-pricing-oct-refund"], policyId: "refund-window@v3", documentId: "doc-pricing-oct-2026", proposal: null, status: "open", changeRequestId: null, createdAt: at(-1, -3),
    },
    { id: "lib-ssl", kind: "stale", title: "TLS certificate expiry date is out of date", detail: "The fact comes from an August monitor export. The monitor now reports a renewed certificate.", factIds: ["f-ssl-expiry"], policyId: null, documentId: "doc-ssl-old", proposal: null, status: "open", changeRequestId: null, createdAt: at(-2) },
    { id: "lib-vat-dup", kind: "duplicate", title: "Two facts describe the VAT registration", detail: "f-vat-reg and f-vat-reg-dup cite the same certificate.", factIds: ["f-vat-reg", "f-vat-reg-dup"], policyId: null, documentId: "doc-vat-cert", proposal: null, status: "open", changeRequestId: null, createdAt: at(-4) },
    { id: "lib-orphan", kind: "orphan", title: "Investor deck 2024 has no linked facts", detail: "Nothing depends on this document. Archive or extract.", factIds: [], policyId: null, documentId: "doc-old-deck", proposal: null, status: "open", changeRequestId: null, createdAt: at(-6) },
    { id: "lib-unverified", kind: "unverified", title: "Unverified claim: retainer SLA in a sales email", detail: "A sales email claims a 2 hour SLA. The MSA says 4 business hours.", factIds: ["f-sla"], policyId: null, documentId: "doc-msa-lanka-logistics", proposal: null, status: "open", changeRequestId: null, createdAt: at(-5) },
  ];

  generateRuns(d, rng, 0.085, 14);
  seedSpecialWork(d);
  generateAccessDecisions(d, rng, 420);
  seedVersioning(d, rng);
  seedEntity(d);
  seedLoops(d, rng);
  seedTrends(d, rng);
  seedMemory(d);
  generateHistoryAudit(d, rng);
  runOvernightReview(d, { now: SEED_NOW - 7.5 * HOUR, actor: { kind: "agent", id: "a-quality", name: "Quality Supervisor" } });
  d.studio = seedStudio(d);
  return d;
}

// ---------------------------------------------------------------- shared generators

function toolNodeId(t: string) {
  return `n:${t}`;
}

function buildGraph(d: TenantData, rng: Rng) {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const typeOrder: GraphNode["type"][] = ["agent", "skill", "tool", "policy", "security", "fact", "document", "template", "sensor"];
  const ring: Record<string, { cx: number; cy: number; r: number }> = {};
  typeOrder.forEach((t, i) => {
    const a = (i / typeOrder.length) * Math.PI * 2;
    ring[t] = { cx: Math.cos(a) * 100, cy: Math.sin(a) * 100, r: 0 };
  });
  const place = (type: GraphNode["type"], idx: number, total: number) => {
    const c = ring[type];
    const a = (idx / Math.max(1, total)) * Math.PI * 2;
    const r = 14 + Math.sqrt(total) * 3.2 * (0.6 + rng.float() * 0.5);
    return { x: c.cx + Math.cos(a) * r, y: c.cy + Math.sin(a) * r };
  };
  const add = (n: Omit<GraphNode, "x" | "y">, idx: number, total: number) => nodes.push({ ...n, ...place(n.type, idx, total) });
  const latestPolicies = d.policies.filter((p) => !p.supersededBy);
  const tools = TOOLS.filter((t) => d.skills.some((s) => s.tools.includes(t.id))).length ? TOOLS : [];
  d.agents.forEach((a, i) => add({ id: `n:${a.id}`, type: "agent", label: a.name, refId: a.id, clusterId: a.clusterId, sensitivity: a.accessLevel === "restricted" ? "confidential" : "internal", requires: { capability: null, roles: [] } }, i, d.agents.length));
  d.skills.filter((s) => s.status !== "draft").forEach((s, i, all) => add({ id: `n:skill:${s.id}`, type: "skill", label: `${s.name} v${s.version}`, refId: s.id, clusterId: s.clusterId, sensitivity: "internal", requires: { capability: null, roles: [] } }, i, all.length));
  tools.forEach((t, i) => add({ id: toolNodeId(t.id), type: "tool", label: t.label, refId: t.id, clusterId: "finebase-platform", sensitivity: t.sensitivity, requires: { capability: t.capability, roles: [] } }, i, tools.length));
  latestPolicies.forEach((p, i) => add({ id: `n:policy:${p.key}`, type: "policy", label: `${p.name} v${p.version}`, refId: p.id, clusterId: p.clusterId, sensitivity: p.criticality >= 4 ? "confidential" : "internal", requires: { capability: null, roles: [] } }, i, latestPolicies.length));
  d.accessRules.forEach((r, i) => add({ id: `n:sec:${r.id}`, type: "security", label: r.name, refId: r.id, clusterId: "finebase-platform", sensitivity: r.sensitivity, requires: { capability: null, roles: r.requiresRoles } }, i, d.accessRules.length));
  d.facts.forEach((f, i) => add({ id: `n:fact:${f.id}`, type: "fact", label: f.statement.length > 48 ? `${f.statement.slice(0, 46)}…` : f.statement, refId: f.id, clusterId: f.clusterId, sensitivity: f.sensitivity, requires: { capability: null, roles: f.sensitivity === "restricted" ? ["finance"] : [] } }, i, d.facts.length));
  d.documents.forEach((x, i) => add({ id: `n:doc:${x.id}`, type: "document", label: x.title, refId: x.id, clusterId: x.clusterId, sensitivity: x.sensitivity, requires: { capability: null, roles: x.sensitivity === "restricted" ? ["finance"] : [] } }, i, d.documents.length));
  d.templates.forEach((t, i) => add({ id: `n:tpl:${t.id}`, type: "template", label: t.name, refId: t.id, clusterId: t.clusterId, sensitivity: "internal", requires: { capability: null, roles: [] } }, i, d.templates.length));
  d.sensors.forEach((s, i) => add({ id: `n:sensor:${s.id}`, type: "sensor", label: s.name, refId: s.id, clusterId: s.clusterId, sensitivity: s.personalData ? "confidential" : "internal", requires: { capability: null, roles: [] } }, i, d.sensors.length));

  const has = new Set(nodes.map((n) => n.id));
  const edge = (source: string, target: string, kind: GraphEdge["kind"], requiresCapability: string | null = null) => {
    if (has.has(source) && has.has(target)) edges.push({ id: `e${edges.length}`, source, target, kind, requiresCapability });
  };
  for (const a of d.agents) {
    for (const s of a.skills) edge(`n:${a.id}`, `n:skill:${s.id}`, "uses");
    for (const s of a.sensors) edge(`n:sensor:${s}`, `n:${a.id}`, "feeds");
    // Each agent can see the tools of the skills in its cluster, so "view as" shows locked edges.
    for (const t of TOOLS) {
      const skillsUsing = d.skills.filter((s) => s.tools.includes(t.id) && s.clusterId === a.clusterId);
      if (skillsUsing.length && (a.capabilities.includes(t.capability) || ["tool:billing.refund", "tool:finance-inbox.read"].includes(t.id) && a.kind === "worker" && (a.id === "a-care" || a.id === "a-compliance" || a.id === "a-billing")))
        edge(`n:${a.id}`, toolNodeId(t.id), "uses", t.capability);
    }
  }
  for (const s of d.skills) {
    for (const t of s.tools) edge(`n:skill:${s.id}`, toolNodeId(t), "uses", TOOLS.find((x) => x.id === t)?.capability ?? null);
    for (const p of s.policies) edge(`n:policy:${p}`, `n:skill:${s.id}`, "governs");
    for (const f of s.templateFields) edge(`n:skill:${s.id}`, `n:tpl:${f.split(".")[0]}`, "fills");
  }
  for (const f of d.facts) {
    for (const e of f.evidence) edge(`n:doc:${e.documentId}`, `n:fact:${f.id}`, "evidences");
    for (const dep of f.dependents) if (dep.type === "policy") edge(`n:fact:${f.id}`, `n:policy:${dep.id.split("@")[0]}`, "evidences");
    for (const dep of f.dependents) if (dep.type === "skill") edge(`n:fact:${f.id}`, `n:skill:${dep.id}`, "depends");
  }
  for (const r of d.accessRules) {
    if (r.appliesTo.startsWith("tool:")) edge(`n:sec:${r.id}`, toolNodeId(r.appliesTo.split("#")[0]), "governs");
  }
  for (const f of d.facts.filter((x) => x.sensitivity !== "internal")) edge("n:sec:sr-pii", `n:fact:${f.id}`, "governs");
  d.graph = { nodes, edges };
}

const SUBJECT_FALLBACK = ["Task"];

function generateRuns(d: TenantData, rng: Rng, factor: number, days: number) {
  let n = 0;
  for (const a of d.agents) {
    const count = Math.max(4, Math.round(a.throughputPerHour * 24 * days * factor));
    const subjects = RUN_SUBJECTS[a.id] ?? (d.tenant.isScaleDemo ? [`${a.name.replace(/ \d+$/, "")} task`] : SUBJECT_FALLBACK);
    for (let i = 0; i < count; i++) {
      const started = SEED_NOW - rng.float() * days * DAY;
      const recent = SEED_NOW - started < 0.3 * HOUR;
      const status: RunStatus = recent && a.status === "working" ? "running" : rng.weighted<RunStatus>([["succeeded", 86], ["escalated", 5], ["failed", 4], ["blocked", 1]]);
      const skill = a.skills.length ? a.skills[Math.floor(rng.float() * a.skills.length)] : { id: "none", version: 1, branch: "main" };
      const tokens = rng.int(800, 12000);
      const latency = rng.int(1800, 42000);
      const custNo = 1000 + rng.int(0, 8999);
      const subject = `${rng.pick(subjects)}${a.id === "a-refund" || a.id === "a-care" ? ` · CUS-${custNo}` : ""}`;
      d.runs.push({
        id: `run-${(++n).toString(36)}-${a.id.slice(2, 6)}`, tenantId: d.tenant.id, clusterId: a.clusterId, agentId: a.id, skill, env: "production", subject, status,
        startedAt: iso(started), endedAt: status === "running" ? null : iso(started + latency),
        escalation: status === "escalated" ? { reason: rng.pick(["Customer asked for a human", "Confidence below threshold", "Outside policy", "Missing information"]), risk: rng.pick(["low", "medium", "high"] as const), since: iso(started + latency), assignee: null, criticality: rng.pick([2, 3] as const) } : null,
        conversationId: null, costTokens: tokens, costUsd: Math.round(tokens * 0.0006) / 100, latencyMs: latency, humanTouch: status === "escalated",
        failureClass: status === "failed" || status === "blocked" ? rng.pick(FAILURE_CLASSES) : null,
      });
    }
  }
  d.runs.sort((x, y) => (x.startedAt < y.startedAt ? 1 : -1));
  // Older escalations are resolved by humans already; keep the queue focused on recent ones.
  for (const r of d.runs) if (r.escalation && SEED_NOW - Date.parse(r.startedAt) > 2 * DAY) r.status = "succeeded";
}

/** Deterministic trace for any run, generated on demand. */
export function generateSteps(run: Run, d: TenantData): TraceStep[] {
  if (d.specialSteps[run.id]) return d.specialSteps[run.id];
  const rng = new Rng(run.id);
  const skill = d.skills.find((s) => s.id === run.skill.id);
  const facts = d.facts.length ? rng.sample(d.facts, 2) : [];
  let t = Date.parse(run.startedAt);
  const step = (kind: TraceStep["kind"], title: string, decision: string, reason: string, extra: Partial<TraceStep> = {}): TraceStep => {
    const dur = kind === "judgment" ? rng.int(900, 6000) : rng.int(40, 900);
    const s: TraceStep = { id: `${run.id}-s${Math.round(t)}`, idx: 0, kind, title, decision, reason, durationMs: dur, at: iso(t), facts: [], access: null, gate: null, tool: null, templateFields: [], costTokens: kind === "judgment" ? rng.int(400, 4000) : 0, ...extra };
    t += dur;
    return s;
  };
  const tool = skill?.tools[0] ?? "tool:chat.reply";
  const cap = TOOLS.find((x) => x.id === tool)?.capability ?? "reply:customer";
  const steps: TraceStep[] = [
    step("retrieval", "Retrieve context", `${facts.length} facts`, "Hybrid search over facts the agent may read", { facts: facts.map((f) => ({ id: f.id, statement: f.statement, validFrom: f.validFrom, validTo: f.validTo })) }),
    step("judgment", skill?.steps.find((s) => s.kind === "judgment")?.text ?? "Decide next action", "Plan ready", "Model judgment against the skill steps"),
    step("access_check", `Access check: ${tool.replace("tool:", "")}`, run.status === "blocked" ? "deny" : "allow", run.status === "blocked" ? `requires capability ${cap}` : "capability held", { access: { action: tool, decision: run.status === "blocked" ? "deny" : "allow", ruleId: run.status === "blocked" ? "capability-grant" : "default-allow" } }),
  ];
  if (run.status !== "blocked") {
    steps.push(step("tool", `Call ${tool.replace("tool:", "")}`, run.status === "failed" ? "error" : "ok", run.status === "failed" ? "Tool returned 502" : "Deterministic tool call", { tool }));
    steps.push(step("quality_gate", "Quality gate", run.status === "failed" ? "fail" : "pass", "Grounding, tone and output schema", { gate: { name: "grounding+tone", passed: run.status !== "failed" } }));
  }
  if (run.status === "escalated") steps.push(step("human", "Escalated to a human", "waiting", run.escalation?.reason ?? "Escalated"));
  if (run.status === "succeeded" && skill?.templateFields[0]) {
    const [tpl, field] = skill.templateFields[0].split(".");
    steps.push(step("tool", "Fill template field", "filled", "Template contract", { templateFields: [{ template: tpl, field, value: "+1" }] }));
  }
  return steps.map((s, i) => ({ ...s, idx: i }));
}

function seedSpecialWork(d: TenantData) {
  const tenantId = d.tenant.id;
  const started = SEED_NOW - 2 * HOUR;
  d.runs.unshift(
    {
      id: "run-1042", tenantId, clusterId: "finebase-platform", agentId: "a-refund", skill: { id: "refund-standard", version: 4, branch: "main" }, env: "production",
      subject: "Refund request · CUS-1042 · annual plan", status: "escalated", startedAt: iso(started), endedAt: iso(started + 38_000),
      escalation: { reason: "Refund of LKR 85,000 requested 41 days after purchase. Outside the 30 day window in refund-window v3 and above the LKR 50,000 auto threshold.", risk: "high", since: iso(started + 38_000), assignee: null, criticality: 3 },
      conversationId: "conv-1042", costTokens: 6120, costUsd: 0.04, latencyMs: 38_000, humanTouch: true, failureClass: null,
    },
    {
      id: "run-2203", tenantId, clusterId: "finebase-platform", agentId: "a-care", skill: { id: "care-goodwill", version: 2, branch: "main" }, env: "production",
      subject: "Chat · refund for outage week · CUS-2203", status: "blocked", startedAt: iso(SEED_NOW - 5 * HOUR), endedAt: iso(SEED_NOW - 5 * HOUR + 9000),
      escalation: { reason: "Care Agent tried billing.refund for LKR 12,000. Access check denied: capability refund:issue not held.", risk: "medium", since: iso(SEED_NOW - 5 * HOUR + 9000), assignee: null, criticality: 2 },
      conversationId: "conv-2203", costTokens: 2210, costUsd: 0.01, latencyMs: 9000, humanTouch: false, failureClass: "access gap",
    },
  );
  const s = (idx: number, kind: TraceStep["kind"], title: string, decision: string, reason: string, offset: number, dur: number, extra: Partial<TraceStep> = {}): TraceStep => ({
    id: `st-${idx}-${title.length}`, idx, kind, title, decision, reason, durationMs: dur, at: iso(started + offset), facts: [], access: null, gate: null, tool: null, templateFields: [], costTokens: kind === "judgment" ? 1800 : 0, ...extra,
  });
  d.specialSteps["run-1042"] = [
    s(0, "retrieval", "Retrieve purchase and refund policy", "3 facts", "Facts valid now, filtered by Refund Agent access", 0, 420, {
      facts: [
        { id: "f-cus-1042", statement: "CUS-1042 bought the annual Growth plan on 28 August 2026 for LKR 85,000", validFrom: "2026-08-28T00:00:00Z", validTo: null },
        { id: "f-refund-window", statement: "Refunds are accepted within 30 days of purchase", validFrom: "2026-01-01T00:00:00Z", validTo: null },
        { id: "f-refund-threshold", statement: "The Refund Agent may refund up to LKR 50,000 without a human", validFrom: "2026-01-01T00:00:00Z", validTo: null },
      ],
    }),
    s(1, "judgment", "Check window and threshold", "Outside policy", "41 days since purchase is more than 30. LKR 85,000 is above LKR 50,000.", 420, 5100),
    s(2, "access_check", "Access check: billing.refund", "allow", "Refund Agent holds refund:issue", 5520, 12, { access: { action: "tool:billing.refund", decision: "allow", ruleId: "sr-refund-tool" } }),
    s(3, "quality_gate", "Policy gate: refund-window v3", "fail", "Request is outside the documented window", 5532, 30, { gate: { name: "refund-window v3", passed: false } }),
    s(4, "tool", "Send holding reply", "sent", "Customer informed that a person will decide", 5562, 640, { tool: "tool:inbox.reply" }),
    s(5, "human", "Escalate to customer care", "waiting", "C3: money above threshold and outside policy needs a human", 6202, 10),
  ];
  d.specialSteps["run-2203"] = [
    s(0, "retrieval", "Retrieve outage impact and account", "2 facts", "Facts valid now", 0, 300, { facts: [{ id: "f-incident", statement: "The 2 October API latency incident was caused by cache eviction", validFrom: "2026-10-02T00:00:00Z", validTo: null }, { id: "f-goodwill-cap", statement: "Goodwill credits are capped at LKR 5,000 per quarter", validFrom: "2026-03-01T00:00:00Z", validTo: null }] }),
    s(1, "judgment", "Decide remedy", "Refund LKR 12,000", "Customer asked for a refund of one week, above the goodwill cap", 300, 4200),
    s(2, "access_check", "Access check: billing.refund", "deny", "Care Agent does not hold capability refund:issue", 4500, 9, { access: { action: "tool:billing.refund", decision: "deny", ruleId: "sr-refund-tool" } }),
    s(3, "tool", "Send handover reply", "sent", "Told the customer a teammate will follow up", 4509, 520, { tool: "tool:chat.reply" }),
  ].map((x) => ({ ...x, at: iso(SEED_NOW - 5 * HOUR + (Date.parse(x.at) - started)) }));

  const msg = (id: string, from: "customer" | "agent" | "human" | "system", author: string, text: string, ms: number, citations: Conversation["messages"][number]["citations"] = []) => ({ id, from, author, text, at: iso(ms), citations });
  d.conversations = [
    {
      id: "conv-1042", tenantId, runId: "run-1042", agentId: "a-refund", customer: "CUS-1042 · K•••••a P•••••a", channel: "email", topic: "Refund request, annual plan", status: "agent", takenOverBy: null,
      reasoningSummary: "Customer bought the annual Growth plan 41 days ago for LKR 85,000 and asks for a full refund after switching tools. Policy refund-window v3 allows 30 days and the auto threshold is LKR 50,000, so this needs a person.",
      proposedActions: [{ id: "pa-1042-1", label: "Refund LKR 85,000 to the original card", tool: "billing.refund", criticality: 3, status: "proposed", reason: "Outside policy and above threshold, a human must decide" }, { id: "pa-1042-2", label: "Offer a prorated credit instead", tool: "billing.credit", criticality: 2, status: "proposed", reason: "Alternative inside goodwill rules" }],
      messages: [
        msg("m1", "customer", "CUS-1042", "Hi, we bought the annual Growth plan on 28 August but our team moved to another tool. Could we get a full refund of the LKR 85,000?", started),
        msg("m2", "agent", "Refund Agent", "Thanks for letting us know. I'm checking your request against our refund policy and a teammate will confirm the next step today.", started + 6000, [{ id: "f-refund-window", label: "Refund window 30 days", validFrom: "2026-01-01T00:00:00Z" }]),
        msg("m3", "system", "Brain", "Escalated to customer care: outside refund window (41 days, policy allows 30) and above the LKR 50,000 auto threshold. Criticality C3.", started + 6200),
      ],
      skillifiedTo: null, updatedAt: iso(started + 6200),
    },
    {
      id: "conv-2203", tenantId, runId: "run-2203", agentId: "a-care", customer: "CUS-2203 · S•••••h M•••••l", channel: "chat", topic: "Refund for outage week", status: "agent", takenOverBy: null,
      reasoningSummary: "Customer wants a refund for the week of the 2 October incident. Care Agent tried a refund but lacks refund:issue, so the action was denied and logged.",
      proposedActions: [{ id: "pa-2203-1", label: "Refund LKR 12,000", tool: "billing.refund", criticality: 2, status: "blocked", reason: "Access check denied: Care Agent lacks refund:issue" }],
      messages: [
        msg("c1", "customer", "CUS-2203", "Your API was slow most of last week. Can I get that week refunded? It's LKR 12,000.", SEED_NOW - 5 * HOUR),
        msg("c2", "agent", "Care Agent", "I'm sorry about the slowdown on 2 October. I've passed your refund request to a teammate who can approve it.", SEED_NOW - 5 * HOUR + 8000, [{ id: "f-incident", label: "Incident RCA 2 October", validFrom: "2026-10-02T00:00:00Z" }]),
        msg("c3", "system", "Brain", "Action blocked: billing.refund denied for Care Agent (rule sr-refund-tool). Logged in the decision log.", SEED_NOW - 5 * HOUR + 8100),
      ],
      skillifiedTo: null, updatedAt: iso(SEED_NOW - 5 * HOUR + 8100),
    },
    ...[
      ["conv-2201", "a-care", "chat", "CUS-2201 · R•••••n", "How to export invoices", "How do I export all my invoices for the year?", "You can export invoices as CSV from Billing, then Invoices, then Export. This arrived in release 4.12.", "f-release-412", "Release 4.12"],
      ["conv-2202", "a-care", "email", "CUS-2202 · D•••••a", "Team seats", "Can we add three more seats mid cycle?", "Yes. Seats are prorated for the rest of your billing period and appear on the next invoice.", "f-monthly-price", "Monthly Growth price"],
      ["conv-2204", "a-sales", "chat", "LEAD-311 · N•••••s", "Quote for mobile app", "We need an MVP mobile app in 10 weeks. Rough cost?", "Thanks! I've booked a discovery call so we can scope it. Our standard engineer hour is on our rate card.", "f-rate-card", "Rate card"],
      ["conv-2205", "a-care", "chat", "CUS-2205 · P•••••a", "Support hours", "Are you open on Poya days?", "Our support hours are 08:00 to 20:00 Sri Lanka time. On Poya days the agent answers and a teammate follows up the next working day.", "f-support-hours", "Support hours"],
    ].map(([id, agent, channel, customer, topic, q, a, fid, flabel], i): Conversation => ({
      id, tenantId, runId: d.runs.find((r) => r.agentId === agent && r.status === "running")?.id ?? d.runs.find((r) => r.agentId === agent)!.id, agentId: agent, customer, channel: channel as "chat" | "email", topic, status: "agent", takenOverBy: null,
      reasoningSummary: `Answered from verified facts (${flabel}).`, proposedActions: [],
      messages: [msg(`${id}-1`, "customer", customer.split(" ")[0], q, SEED_NOW - (i + 1) * 9 * 60_000), msg(`${id}-2`, "agent", d.agents.find((x) => x.id === agent)!.name, a, SEED_NOW - (i + 1) * 9 * 60_000 + 7000, [{ id: fid, label: flabel, validFrom: d.facts.find((f) => f.id === fid)?.validFrom ?? iso(SEED_NOW) }])],
      skillifiedTo: null, updatedAt: iso(SEED_NOW - (i + 1) * 9 * 60_000 + 7000),
    })),
  ];
}

function generateAccessDecisions(d: TenantData, rng: Rng, count: number) {
  const out: AccessDecision[] = [];
  const recentRuns = d.runs.slice(0, Math.min(d.runs.length, count * 2));
  for (let i = 0; i < count && recentRuns.length; i++) {
    const run = recentRuns[rng.int(0, recentRuns.length - 1)];
    const skill = d.skills.find((s) => s.id === run.skill.id);
    const tool = skill?.tools[0] ?? "tool:chat.reply";
    const deny = run.status === "blocked";
    out.push({
      id: `ad-${i}`, tenantId: d.tenant.id, at: run.startedAt, principal: run.agentId, onBehalfOf: null, action: tool, resource: tool.replace("tool:", ""),
      decision: deny ? "deny" : "allow", ruleId: deny ? "capability-grant" : "default-allow", reason: deny ? `requires capability ${TOOLS.find((t) => t.id === tool)?.capability ?? "unknown"}` : "capability held",
      latencyMs: Math.round((2 + rng.float() * 9) * 10) / 10, runId: run.id,
    });
  }
  out.push({ id: "ad-2203", tenantId: d.tenant.id, at: iso(SEED_NOW - 5 * HOUR + 4500), principal: "a-care", onBehalfOf: null, action: "tool:billing.refund", resource: "billing.refund (LKR 12,000)", decision: "deny", ruleId: "sr-refund-tool", reason: "requires capability refund:issue, which Care Agent does not hold", latencyMs: 4.1, runId: "run-2203" });
  out.push({ id: "ad-1042", tenantId: d.tenant.id, at: iso(SEED_NOW - 2 * HOUR + 5520), principal: "a-refund", onBehalfOf: null, action: "tool:billing.refund", resource: "billing.refund (LKR 85,000)", decision: "allow", ruleId: "sr-refund-tool", reason: "capability refund:issue held, amount check left to policy gate", latencyMs: 3.2, runId: "run-1042" });
  d.accessDecisions = out.sort((a, b) => (a.at < b.at ? 1 : -1));
}

function seedVersioning(d: TenantData, rng: Rng) {
  const tenantId = d.tenant.id;
  const sys = { kind: "system" as const, id: "system", name: "Brain" };
  d.branches = [
    { id: "br-main", tenantId, name: "main", env: "production", base: null, head: null, status: "protected", description: "Production. Merging deploys.", createdBy: sys, createdAt: at(-400) },
    { id: "br-staging", tenantId, name: "staging", env: "staging", base: "main", head: null, status: "protected", description: "Shadow mode on live traffic, no actions.", createdBy: sys, createdAt: at(-400) },
  ];
  // History on main: one commit per skill and policy version, newest last.
  const history: Commit[] = [];
  const authors = d.humans.filter((h) => h.tier !== "L3");
  for (const s of d.skills) {
    for (let v = 1; v <= s.version; v++) {
      history.push({ id: "", tenantId, branch: "main", parentId: null, author: v === 1 ? { kind: "human", id: s.dri, name: d.humans.find((h) => h.id === s.dri)?.name ?? s.dri } : rng.chance(0.4) ? { kind: "agent", id: "a-quality", name: "Quality Supervisor" } : { kind: "human", id: rng.pick(authors).id, name: rng.pick(authors).name },
        message: v === 1 ? `Add skill ${s.name}` : `${s.name}: ${rng.pick(["tighten step wording", "add citation requirement", "split tool call", "raise confidence threshold", "add quality gate"])}`,
        changes: [{ op: v === 1 ? "add" : "modify", nodeType: "skill", nodeId: s.id, label: s.name, field: v === 1 ? null : "steps", before: v === 1 ? null : `v${v - 1}`, after: `v${v}` }],
        criticality: v === 1 ? 3 : 2, evidence: [], createdAt: at(-(s.version - v + 1) * 18 - (hashString(s.id) % 15)), tag: null });
    }
  }
  for (const p of d.policies) {
    history.push({ id: "", tenantId, branch: "main", parentId: null, author: { kind: "human", id: p.dri, name: d.humans.find((h) => h.id === p.dri)?.name ?? p.dri }, message: p.version === 1 ? `Add policy ${p.name}` : `${p.name}: ${p.statement}`, changes: [{ op: p.version === 1 ? "add" : "modify", nodeType: "policy", nodeId: p.key, label: p.name, field: "rule", before: null, after: p.statement }], criticality: p.criticality, evidence: p.evidence, createdAt: p.recordedAt, tag: null });
  }
  history.sort((a, b) => (a.createdAt < b.createdAt ? -1 : 1));
  let parent: string | null = null;
  history.forEach((c, i) => {
    c.id = `c${(hashString(c.message + i) % 0xfffffff).toString(16).padStart(7, "0")}`;
    c.parentId = parent;
    parent = c.id;
    if (i % 12 === 11) c.tag = `release-${c.createdAt.slice(0, 10)}`;
  });
  d.commits = history;
  d.branches[0].head = parent;
  d.branches[1].head = parent;

  // Security Sentinel proposal for flow 5: needs two L1 approvals.
  const grantBranch: Branch = { id: "br-sentinel-grant", tenantId, name: "sandbox/sentinel-care-refund-grant", env: "sandbox", base: "main", head: "c5e1a0001", status: "open", description: "Proposed grant after denied refund attempts", createdBy: { kind: "agent", id: "a-sentinel", name: "Security Sentinel" }, createdAt: at(0, -4) };
  d.branches.push(grantBranch);
  d.commits.push({ id: "c5e1a0001", tenantId, branch: grantBranch.name, parentId: parent, author: { kind: "agent", id: "a-sentinel", name: "Security Sentinel" }, message: "Grant Care Agent refund:issue up to LKR 10,000", changes: [{ op: "modify", nodeType: "agent", nodeId: "a-care", label: "Care Agent", field: "capabilities", before: "reply:customer, credit:goodwill, crm:write", after: "reply:customer, credit:goodwill, crm:write, refund:issue (max LKR 10,000)" }], criticality: 4, evidence: ["ad-2203"], createdAt: at(0, -4), tag: null });
  d.changeRequests.push({
    id: "cr-sentinel-grant", tenantId, title: "Grant Care Agent refund capability up to LKR 10,000", kind: "security", fromBranch: grantBranch.name, toBranch: "main", commits: ["c5e1a0001"],
    plainDiff: ["Care Agent gains capability refund:issue, capped at LKR 10,000 per refund.", "Refunds above LKR 10,000 still go to the Refund Agent or a human."],
    changes: d.commits.at(-1)!.changes,
    impactPreview: { runsReplayed: 318, decisionsChanged: 6, predictedRisk: "medium", summary: "6 of the last 318 Care conversations asked for a refund under LKR 10,000 and were escalated. With this grant they would resolve without a human.", examples: [{ runId: "run-2203", before: "Denied, escalated", after: "Still escalated: LKR 12,000 is above the LKR 10,000 cap" }] },
    tests: { suite: "eval-care-goodwill + access suite", total: 42, passed: 42, failed: 0, passK: 0.95, k: 8, ranAt: at(0, -3.5) },
    approvalId: "apr-sentinel-grant", status: "awaiting_approval", criticality: 4, criticalityReasons: ["capability grant starts at C4", "touches money"],
    drafter: { kind: "agent", id: "a-sentinel", name: "Security Sentinel" }, dri: "h-hcs", clusters: ["finebase-platform"], createdAt: at(0, -4), mergedAt: null, coolingUntil: null, correlationId: "flow-blocked-action",
  });
  d.approvals.push({
    id: "apr-sentinel-grant", tenantId, subject: { kind: "change_request", id: "cr-sentinel-grant" }, title: "Grant Care Agent refund capability up to LKR 10,000",
    summary: "Security Sentinel proposes this after the Care Agent was denied billing.refund. Two L1 approvers are needed because it changes what an agent may do with money.",
    criticality: 4, requiredApprovers: { tier: "L1", count: 2, roles: [] }, votes: [], dueAt: at(2), createdAt: at(0, -3.5), status: "pending", delegatedTo: null, dri: "h-hcs",
    drafter: { kind: "agent", id: "a-sentinel", name: "Security Sentinel" }, evidence: ["ad-2203", "run-2203"], correlationId: "flow-blocked-action",
  });

  // A pending C3 policy draft from the knowledge steward.
  d.branches.push({ id: "br-ks-identity", tenantId, name: "sandbox/data-request-identity-check", env: "sandbox", base: "main", head: "c7d2b0002", status: "open", description: "New policy for data requests", createdBy: { kind: "human", id: "h-ks", name: "Dilini Wickramasinghe" }, createdAt: at(-1) });
  d.commits.push({ id: "c7d2b0002", tenantId, branch: "sandbox/data-request-identity-check", parentId: parent, author: { kind: "human", id: "h-ks", name: "Dilini Wickramasinghe" }, message: "Add policy: identity check before data requests", changes: [{ op: "add", nodeType: "policy", nodeId: "data-request-identity", label: "Identity check for data requests", field: null, before: null, after: "Verify identity with two factors before any access or deletion request." }], criticality: 3, evidence: ["doc-privacy-notice"], createdAt: at(-1), tag: null });
  d.changeRequests.push({
    id: "cr-identity-policy", tenantId, title: "New policy: identity check before data requests", kind: "policy", fromBranch: "sandbox/data-request-identity-check", toBranch: "main", commits: ["c7d2b0002"],
    plainDiff: ["New policy: verify identity with two factors before any personal data access or deletion request."], changes: d.commits.at(-1)!.changes,
    impactPreview: { runsReplayed: 44, decisionsChanged: 3, predictedRisk: "low", summary: "3 of the last 44 data requests would have asked for a second factor first.", examples: [] },
    tests: { suite: "eval-care-answer", total: 30, passed: 30, failed: 0, passK: 0.93, k: 8, ranAt: at(-1, 1) },
    approvalId: "apr-identity-policy", status: "awaiting_approval", criticality: 4, criticalityReasons: ["new policy starts at C3", "moves up one level because it touches personal data"],
    drafter: { kind: "human", id: "h-ks", name: "Dilini Wickramasinghe" }, dri: "h-founder", clusters: ["finebase-platform"], createdAt: at(-1), mergedAt: null, coolingUntil: null, correlationId: "cr-identity-policy",
  });
  d.approvals.push({ id: "apr-identity-policy", tenantId, subject: { kind: "change_request", id: "cr-identity-policy" }, title: "New policy: identity check before data requests", summary: "Adds a two factor identity check before any personal data request is handled.", criticality: 4, requiredApprovers: { tier: "L1", count: 2, roles: [] }, votes: [], dueAt: at(3), createdAt: at(-1, 1), status: "pending", delegatedTo: null, dri: "h-founder", drafter: { kind: "human", id: "h-ks", name: "Dilini Wickramasinghe" }, evidence: ["doc-privacy-notice"], correlationId: "cr-identity-policy" });

  // Merged history change requests
  const merged = d.commits.filter((c) => c.branch === "main").slice(-8);
  merged.forEach((c, i) => {
    d.changeRequests.push({
      id: `cr-h${i}`, tenantId, title: c.message, kind: c.changes[0].nodeType === "policy" ? "policy" : "skill", fromBranch: `sandbox/${c.changes[0].nodeId}-${i}`, toBranch: "main", commits: [c.id], plainDiff: [c.message], changes: c.changes,
      impactPreview: { runsReplayed: 120 + i * 13, decisionsChanged: i % 4, predictedRisk: "low", summary: `${i % 4} of ${120 + i * 13} replayed runs changed decision.`, examples: [] },
      tests: { suite: `eval-${c.changes[0].nodeId}`, total: 30, passed: 30, failed: 0, passK: 0.9, k: 8, ranAt: c.createdAt }, approvalId: null, status: "merged", criticality: c.criticality, criticalityReasons: [],
      drafter: c.author, dri: "h-founder", clusters: ["finebase-platform"], createdAt: c.createdAt, mergedAt: c.createdAt, coolingUntil: null, correlationId: `cr-h${i}`,
    });
  });
}

function seedEntity(d: TenantData) {
  const tenantId = d.tenant.id;
  const ob = (id: string, title: string, cluster: string, category: Obligation["category"], jurisdiction: string, dueDays: number, items: [string, string, string | null][], dri: string, note: string): Obligation => {
    const requiredEvidence = items.map(([key, label, satisfiedBy]) => ({ key, label, satisfiedBy }));
    const readiness = readinessOf(requiredEvidence);
    const dueAt = at(dueDays);
    return { id, tenantId, clusterId: cluster, title, jurisdiction, category, dueAt, prepareBy: at(dueDays - 7), requiredEvidence, readiness, status: statusOf(readiness, dueAt, SEED_NOW), dri, isSample: true, note };
  };
  d.obligations = [
    ob("ob-vat-sep", "VAT return, September 2026", "finance-compliance", "tax", "Sri Lanka, Inland Revenue (sample)", 21, [["sales-register", "Sales register for September", "f-sales-register-sep"], ["input-invoices", "Input VAT invoices for September", null], ["bank-statement", "Bank statement for September", null]], "h-fd", "Sample deadline. The system prepares and collects proof. A human files."),
    ob("ob-apit-sep", "APIT remittance, September 2026", "finance-compliance", "tax", "Sri Lanka, Inland Revenue (sample)", 7, [["payroll", "Payroll summary", "f-payroll-sep"], ["apit", "APIT computation", "f-apit-sep"]], "h-fd", "Sample deadline."),
    ob("ob-epf-sep", "EPF contributions, September 2026", "finance-compliance", "statutory", "Sri Lanka, EPF (sample)", 22, [["schedule", "Contribution schedule", "f-epf-schedule"], ["payment", "Payment proof", null]], "h-fd", "Sample deadline."),
    ob("ob-etf-sep", "ETF contributions, September 2026", "finance-compliance", "statutory", "Sri Lanka, ETF Board (sample)", 22, [["schedule", "Contribution schedule", null], ["payment", "Payment proof", null]], "h-fd", "Sample deadline."),
    ob("ob-it-inst", "Income tax instalment, Q2 (sample)", "finance-compliance", "tax", "Sri Lanka, Inland Revenue (sample)", 38, [["estimate", "Profit estimate", null], ["computation", "Instalment computation", null]], "h-fd", "Sample deadline."),
    ob("ob-annual-return", "Company annual return 2026", "finance-compliance", "statutory", "Sri Lanka, Registrar of Companies (sample)", 45, [["shareholders", "Shareholder register", "f-shareholders"], ["agm", "AGM minutes", null]], "h-founder", "Sample deadline."),
    ob("ob-domain", "Domain renewal finebase.lk", "finance-compliance", "renewal", "Domain registry", 30, [["invoice", "Renewal invoice", "f-domain"]], "h-fd", "Sample."),
    ob("ob-ssl", "TLS certificate renewal app.finebase.lk", "finance-compliance", "renewal", "Certificate authority", 43, [["order", "Renewal order", null]], "h-sec", "Sample."),
    ob("ob-retainer", "Lanka Logistics retainer renewal", "finance-compliance", "contract", "Contract", 53, [["proposal", "Renewal proposal", null], ["msa", "Current MSA", "f-retainer-renewal"]], "h-founder", "Sample."),
    ob("ob-cloud", "Cloud hosting subscription", "finance-compliance", "renewal", "Vendor", 26, [["budget", "Budget approval", "f-cloud-budget"]], "h-fd", "Sample."),
  ];
  d.evidenceRequests = [
    { id: "er-epf-payment", tenantId, obligationId: "ob-epf-sep", evidenceKey: "payment", item: "EPF payment proof for September", requestedFrom: "h-fd", status: "open", dueAt: at(15), createdAt: at(-3), escalationLevel: 0, suggestedGrant: null, fulfilledBy: null },
  ];
  d.grants = [
    { id: "g-accounting", tenantId, source: "Accounting exports", scope: "read:monthly-exports", retentionDays: 2555, agents: ["a-compliance", "a-billing"], revoke: "Revoke from Security and access at any time", status: "active", requestedBy: "a-compliance", approvalId: null, createdAt: at(-200) },
  ];
  d.risks = [
    { id: "risk-vat", title: "VAT return evidence incomplete", likelihood: "medium", impact: "high", owner: "h-fd", mitigation: "Readiness scheduler requests input invoices and bank statement 21 days ahead.", linkedObligation: "ob-vat-sep" },
    { id: "risk-etf", title: "ETF schedule not prepared", likelihood: "medium", impact: "medium", owner: "h-fd", mitigation: "Dispatch Compliance Agent to draft from payroll.", linkedObligation: "ob-etf-sep" },
    { id: "risk-refund-policy", title: "Refund policy drift", likelihood: "high", impact: "medium", owner: "h-hcs", mitigation: "Librarian conflict proposal pending.", linkedObligation: null },
    { id: "risk-ssl", title: "TLS certificate fact is stale", likelihood: "low", impact: "high", owner: "h-sec", mitigation: "Refresh from certificate monitor.", linkedObligation: "ob-ssl" },
    { id: "risk-single-dri", title: "Finance approvals depend on one person", likelihood: "medium", impact: "high", owner: "h-founder", mitigation: "Add a delegate for C4 finance approvals.", linkedObligation: null },
  ];
  d.readinessRules = [
    { id: "rr-tax", target: "Tax obligations", requires: "Every evidence item verified by a fact with provenance", checkEvery: "Hourly", escalationDays: [21, 14, 7, 2], lastRunAt: at(-1) },
    { id: "rr-statutory", target: "Statutory filings", requires: "Schedule and payment proof", checkEvery: "Daily", escalationDays: [21, 14, 7, 2], lastRunAt: at(-1) },
    { id: "rr-renewals", target: "Renewals", requires: "Invoice or order 30 days ahead", checkEvery: "Daily", escalationDays: [30, 14, 7], lastRunAt: at(-1) },
    { id: "rr-templates", target: "Templates", requires: "Required fields fresh per template rule", checkEvery: "Hourly", escalationDays: [2, 1], lastRunAt: at(0, -1) },
  ];
}

function seedLoops(d: TenantData, rng: Rng) {
  const tenantId = d.tenant.id;
  const history = (base: number) => Array.from({ length: 14 }, (_, i) => ({ day: iso(SEED_NOW - (13 - i) * DAY).slice(0, 10), runs: Math.round(base * (0.8 + rng.float() * 0.4)), success: 0.82 + rng.float() * 0.15 }));
  const loop = (id: string, name: string, cluster: string, description: string, stages: [string, string[], string, string, number][], runs: number, dri: string, experiments: string[] = []): Loop => ({
    id, tenantId, clusterId: cluster, name, description, runs7d: runs, successRate: 0.86 + rng.float() * 0.1, autonomyRate: 0.7 + rng.float() * 0.25, history: history(runs / 7), experiments, dri,
    stages: (["sensor", "policy", "tool", "gate", "learning"] as const).map((key, i) => ({ key, label: stages[i][0], refs: stages[i][1], metric: { label: stages[i][2], value: stages[i][3], trend: rng.float() * 0.2 - 0.08 }, pending: stages[i][4] })),
  });
  d.loops = [
    loop("loop-care", "Customer care", "finebase-platform", "Chat and email answers with goodwill credits.", [["Chat, inbox, usage", ["s-chat", "s-support-inbox", "s-usage"], "events/h", "671", 0], ["Tone and masking", ["public-reply-tone", "pii-masking"], "conformance", "94%", 0], ["chat.reply, billing.credit", ["tool:chat.reply", "tool:billing.credit"], "calls/day", "312", 0], ["Grounding and tone gate", ["gate"], "pass rate", "96%", 1], ["Weekly care report", ["tpl-care-weekly"], "fixes this week", "4", 0]], 2100, "h-hcs"),
    loop("loop-refunds", "Refunds", "finebase-platform", "Refunds inside policy, escalations outside it.", [["Inbox, payments", ["s-support-inbox", "s-payments"], "requests/day", "11", 0], ["Refund window, threshold", ["refund-window", "refund-auto-threshold"], "conformance", "62%", 1], ["billing.refund", ["tool:billing.refund"], "refunds/day", "8", 0], ["Policy gate", ["gate"], "pass rate", "81%", 1], ["Refund register", ["tpl-refund-register"], "drafts", "1", 1]], 77, "h-hcs"),
    loop("loop-website", "Website UX", "finebase-platform", "Friction found in Clarity becomes experiments on sandbox branches.", [["Clarity, analytics, click sensors", ["s-clarity", "s-analytics", "s-clicks"], "rage clicks/7d", "312", 0], ["Pricing and legal pages", ["pricing-change"], "pages guarded", "3", 0], ["experiments.create", ["tool:experiments.create"], "experiments", "3", 0], ["A/B significance gate", ["gate"], "min sample", "2,000", 1], ["Experiment report", ["tpl-experiments"], "learnings", "2", 0]], 21, "h-hcs", ["exp-pricing-toggle", "exp-signup-copy", "exp-careers-cta"]),
    loop("loop-revenue", "Revenue recovery", "finance-compliance", "Failed payments and receivables.", [["Payments, bank feed", ["s-payments", "s-bank-feed"], "failed/day", "4", 0], ["Write offs", ["write-off"], "conformance", "97%", 0], ["billing.retry-charge", ["tool:billing.retry"], "retries/day", "6", 0], ["Recovery gate", ["gate"], "recovered", "71%", 0], ["Revenue health", ["tpl-revenue-health"], "fresh", "yes", 0]], 290, "h-fd"),
    loop("loop-readiness", "Obligation readiness", "finance-compliance", "Finds missing proof before deadlines.", [["Obligations calendar, exports", ["s-obligations", "s-accounting"], "obligations", "10", 0], ["VAT evidence pack", ["vat-evidence"], "rules", "4", 0], ["evidence.request", ["tool:evidence.request"], "requests open", "1", 0], ["Human files", ["gate"], "C4 sign off", "manual", 2], ["Obligation readiness", ["tpl-obligations"], "green", "4 of 10", 0]], 70, "h-fd"),
    loop("loop-freshness", "Knowledge freshness", "finebase-platform", "Librarian keeps ground truth worth retrieving from.", [["All sources", ["s-accounting", "s-contracts"], "new docs/7d", "9", 0], ["Ground truth rules", ["data-retention"], "verified facts", "24", 0], ["graph.commit", ["tool:graph.commit"], "proposals", "1", 1], ["L1 approval for C3", ["gate"], "waiting", "1", 1], ["Freshness report", ["tpl-freshness"], "queue", "5", 0]], 35, "h-ks"),
  ];
  d.experiments = [
    { id: "exp-pricing-toggle", loopId: "loop-website", title: "Clearer pricing toggle", hypothesis: "A segmented Monthly | Annual control that shows the annual saving will cut rage clicks and lift plan selection.", signal: "312 rage clicks on the pricing toggle in 7 days, 41% of pricing page sessions (Microsoft Clarity).", proposedBy: "a-insights", branch: null, variants: [{ id: "A", name: "Current toggle", traffic: 0.5, conversion: null }, { id: "B", name: "Segmented control with saving", traffic: 0.5, conversion: null }], status: "proposed", impact: null, learning: null, changeRequestId: null, criticality: 3, startedAt: null, endedAt: null },
    { id: "exp-signup-copy", loopId: "loop-website", title: "Signup button copy", hypothesis: "'Start free trial' beats 'Sign up'.", signal: "Dead clicks near the signup button.", proposedBy: "a-insights", branch: "sandbox/exp-signup-copy", variants: [{ id: "A", name: "Sign up", traffic: 0.5, conversion: 0.031 }, { id: "B", name: "Start free trial", traffic: 0.5, conversion: 0.036 }], status: "kept", impact: "positive", learning: "Action words that name the outcome convert better on signup. Applied to other CTAs.", changeRequestId: null, criticality: 2, startedAt: at(-30), endedAt: at(-16) },
    { id: "exp-careers-cta", loopId: "loop-website", title: "Careers page hero", hypothesis: "Showing open roles first increases applications.", signal: "Low scroll depth on careers.", proposedBy: "a-insights", branch: "sandbox/exp-careers-cta", variants: [{ id: "A", name: "Story first", traffic: 0.5, conversion: 0.022 }, { id: "B", name: "Roles first", traffic: 0.5, conversion: 0.019 }], status: "discarded", impact: "negative", learning: "Candidates read the story before roles. Keep story first.", changeRequestId: null, criticality: 2, startedAt: at(-45), endedAt: at(-31) },
  ];
}

function generateHistoryAudit(d: TenantData, rng: Rng) {
  const out: AuditEvent[] = [];
  for (const c of d.commits.filter((x) => x.branch === "main").slice(-60)) {
    out.push({ id: `au-${c.id}`, tenantId: d.tenant.id, at: c.createdAt, actor: c.author, action: "commit.merged", target: { type: c.changes[0].nodeType, id: c.changes[0].nodeId, label: c.changes[0].label }, env: "production", criticality: c.criticality, detail: c.message, correlationId: null });
  }
  for (const r of d.runs.slice(0, 120)) {
    const agent = d.agents.find((a) => a.id === r.agentId)!;
    out.push({ id: `au-${r.id}`, tenantId: d.tenant.id, at: r.startedAt, actor: { kind: "agent", id: agent.id, name: agent.name }, action: `run.${r.status}`, target: { type: "run", id: r.id, label: r.subject }, env: r.env, criticality: r.escalation?.criticality ?? 0, detail: r.escalation?.reason ?? `Skill ${r.skill.id} v${r.skill.version}`, correlationId: r.conversationId ? `conv:${r.conversationId}` : null });
  }
  for (const a of d.accessDecisions.filter((x) => x.decision === "deny")) {
    out.push({ id: `au-${a.id}`, tenantId: d.tenant.id, at: a.at, actor: { kind: "agent", id: a.principal, name: d.agents.find((x) => x.id === a.principal)?.name ?? a.principal }, action: "access.denied", target: { type: "tool", id: a.action, label: a.resource }, env: "production", criticality: 2, detail: a.reason, correlationId: a.id === "ad-2203" ? "flow-blocked-action" : null });
  }
  out.push({ id: "au-pii-1", tenantId: d.tenant.id, at: at(-1, -2), actor: { kind: "human", id: "h-hcs", name: "Ishara Fernando" }, action: "pii.revealed", target: { type: "conversation", id: "conv-2202", label: "Customer email" }, env: "production", criticality: 2, detail: "Revealed customer email to resolve a billing contact", correlationId: null });
  void rng;
  d.audit = out.sort((a, b) => (a.at < b.at ? 1 : -1));
  d.notifications = [
    { id: "nt-1", tenantId: d.tenant.id, at: at(0, -3.5), to: null, title: "C4 approval needs two L1 approvers", body: "Grant Care Agent refund capability up to LKR 10,000", href: "/l1/approvals/apr-sentinel-grant", kind: "approval", read: false },
    { id: "nt-2", tenantId: d.tenant.id, at: at(0, -2), to: "h-op", title: "Escalation: refund outside policy", body: "CUS-1042 asks for LKR 85,000, 41 days after purchase", href: "/l3/conversations/conv-1042", kind: "escalation", read: false },
    { id: "nt-3", tenantId: d.tenant.id, at: at(-1, -3), to: "h-ks", title: "Librarian found a conflict", body: "Refund window conflicts with the October pricing sheet", href: "/l2/vault", kind: "info", read: false },
  ];
}

// ---------------------------------------------------------------- Scale Demo

export function buildScale(): TenantData {
  const rng = new Rng("scale-demo-seed-1");
  const tenantId = "scale";
  const clusterNames = ["Retail Banking", "Card Services", "Wealth", "Insurance", "Lending", "Treasury", "Marketing", "People Ops"];
  const d: TenantData = {
    tenant: { id: tenantId, name: "Scale Demo", currency: "USD", timezone: "UTC", locale: "en-US", brand: { primary: "#0f766e", mark: "SD" }, clusters: [], criticalityThresholds: { ...THRESHOLDS, refundAutoLimitMinor: 50_000 }, isScaleDemo: true },
    ...emptyData(),
  };
  d.clusters = clusterNames.map((name, i) => ({
    id: `sc-${i}`, tenantId, name, description: `${name} operations (generated).`, status: i < 6 ? "active" : "planned", connectors: [], dri: i < 6 ? `sh-${i % 3}` : null,
    health: 70 + rng.int(0, 29), autonomyRate: 0.6 + rng.float() * 0.35, escalationRate: rng.float() * 0.1, moneyAtStakeMinor: rng.int(1, 90) * 1_000_000_00, openRisks: rng.int(0, 14), costPerTaskUsd: Math.round((0.02 + rng.float() * 0.3) * 100) / 100,
  }));
  d.tenant.clusters = d.clusters.map((c) => c.id);
  const roles: [string, string, "L1" | "L2" | "L3", number][] = [["Chief Executive", "dri", "L1", 4], ["Chief Financial Officer", "finance", "L1", 4], ["Chief Customer Officer", "customer-success", "L1", 4], ["Knowledge Steward", "knowledge-steward", "L2", 2], ["AI Operations Lead", "ai-ops", "L2", 2], ["Security Officer", "security", "L2", 2], ["Operations Analyst", "care-operator", "L3", 0]];
  d.humans = roles.map(([title, role, tier, max], i) => ({ id: `sh-${i}`, tenantId, name: `${["Alex", "Sam", "Jordan", "Riley", "Morgan", "Casey", "Taylor"][i]} ${["Lee", "Ng", "Okafor", "Silva", "Novak", "Haddad", "Kim"][i]}`, title, tier, roles: [role, ...(tier === "L1" ? ["dri"] : [])], attributes: { clearance: tier === "L3" ? "internal" : "restricted", department: role }, driOf: [], maxApprovalCriticality: max as 0 | 2 | 4, color: ["#4338ca", "#0369a1", "#be123c", "#047857", "#b45309", "#6d28d9", "#0f766e"][i] }));
  const roleNames = ["Care", "Claims", "Fraud", "Collections", "Onboarding", "KYC", "Payments", "Reconciliation", "Reporting", "Pricing", "Disputes", "Underwriting"];
  const active = d.clusters.filter((c) => c.status === "active");
  for (let i = 0; i < 400; i++) {
    const cluster = active[i % active.length];
    d.skills.push({ id: `sk-${i}`, tenantId, name: `${rng.pick(roleNames)} procedure ${i}`, version: rng.int(1, 9), branch: "main", status: "active", clusterId: cluster.id, trigger: "Event matched by resolver", inputs: ["events"], steps: [{ id: `sk-${i}-1`, kind: "retrieval", text: "Retrieve context", tool: null }, { id: `sk-${i}-2`, kind: "judgment", text: "Decide", tool: null }, { id: `sk-${i}-3`, kind: "tool", text: "Act", tool: `tool:t${i % 60}` }], tools: [`tool:t${i % 60}`], policies: [`pol-${i % 60}`], requiredCapabilities: [`cap:${i % 60}`], outputs: ["Result"], templateFields: [`stpl-${i % 80}.f`], evalSuite: { id: `eval-${i}`, cases: rng.int(10, 80), passRate: 0.7 + rng.float() * 0.29 }, health: { taskSuccess: 0.7 + rng.float() * 0.29, consistencyPassK: 0.65 + rng.float() * 0.3, k: 8, conformance: 0.6 + rng.float() * 0.38 }, agentIds: [], dri: `sh-${i % 3}`, updatedAt: iso(SEED_NOW - rng.int(1, 200) * DAY), origin: "authored" });
  }
  for (let i = 0; i < 320; i++) {
    const cluster = active[i % active.length];
    const skills = rng.sample(d.skills.filter((s) => s.clusterId === cluster.id), 3);
    skills.forEach((s) => s.agentIds.push(`sa-${i}`));
    const working = rng.chance(0.62);
    d.agents.push({ id: `sa-${i}`, tenantId, name: `${rng.pick(roleNames)} Agent ${String(i).padStart(3, "0")}`, kind: i % 40 === 0 ? "supervisor" : "worker", tier: i % 40 === 0 ? "L2" : "L3", clusterId: cluster.id, description: "Generated agent for the scale demo.", autonomy: rng.pick(["trainee", "supervised", "autonomous"] as const), skills: skills.map((s) => ({ id: s.id, version: s.version, branch: "main" })), capabilities: skills.flatMap((s) => s.requiredCapabilities), accessLevel: rng.pick(["internal", "confidential", "restricted"] as const), sensors: [`ss-${i % 120}`], templates: [`stpl-${i % 80}`], policies: skills.flatMap((s) => s.policies), status: working ? "working" : rng.weighted([["idle", 80], ["blocked", 8], ["error", 6], ["paused", 6]] as const), workKind: working ? rng.pick(["retrieval", "judgment", "tool"] as const) : null, dri: `sh-${i % 3}`, queueDepth: working ? rng.int(0, 40) : 0, throughputPerHour: 1 + rng.float() * 8, errorRate: rng.float() * 0.08, costTodayUsd: Math.round(rng.float() * 4000) / 100, taskSuccess: 0.7 + rng.float() * 0.29, training: [] });
  }
  for (let i = 0; i < 60; i++) d.policies.push({ id: `pol-${i}@v1`, key: `pol-${i}`, tenantId, name: `Policy ${i}`, version: 1, branch: "main", clusterId: active[i % active.length].id, statement: `Generated policy ${i}.`, rule: { kind: "generated", params: { n: i } }, criticality: rng.pick([1, 2, 3, 4] as const), validFrom: iso(SEED_NOW - rng.int(30, 400) * DAY), validTo: null, recordedAt: iso(SEED_NOW - rng.int(30, 400) * DAY), supersededBy: null, evidence: [], freshness: { intervalClosed: false, driftPointAt: rng.chance(0.1) ? iso(SEED_NOW - rng.int(1, 20) * DAY) : null, conformance: 0.6 + rng.float() * 0.38, conflictingEvidence: rng.chance(0.1) ? 1 : 0, outdatedRelianceRate: rng.float() * 0.1 }, dependents: [], dri: `sh-${i % 3}` });
  for (let i = 0; i < 400; i++) d.documents.push({ id: `sd-${i}`, tenantId, clusterId: active[i % active.length].id, title: `Document ${i}.pdf`, source: "Upload", type: rng.pick(["policy", "ledger", "contract", "report"]), sensitivity: rng.pick(["internal", "confidential", "restricted"] as const), extractionStatus: "done", linkedFacts: [], retentionDays: 2555, filingRule: "general", uploadedBy: `sh-${i % 7}`, uploadedAt: iso(SEED_NOW - rng.int(1, 300) * DAY), sizeKb: rng.int(20, 4000), personalData: rng.chance(0.2) });
  for (let i = 0; i < 900; i++) d.facts.push({ id: `sf-${i}`, tenantId, clusterId: active[i % active.length].id, statement: `Generated fact ${i}`, subject: `subject ${i % 90}`, value: String(rng.int(1, 1000)), validFrom: iso(SEED_NOW - rng.int(1, 400) * DAY), validTo: null, recordedAt: iso(SEED_NOW - rng.int(1, 400) * DAY), evidence: [{ documentId: `sd-${i % 400}`, page: 1, quote: "…" }], verifiedBy: `sh-3`, status: rng.weighted([["verified", 90], ["stale", 5], ["unverified", 5]] as const), sensitivity: rng.pick(["internal", "confidential", "restricted"] as const), dependents: [] });
  for (let i = 0; i < 120; i++) d.sensors.push({ id: `ss-${i}`, tenantId, clusterId: active[i % active.length].id, name: `Sensor ${i}`, source: "Generated", kind: rng.pick(["website", "analytics", "inbox", "payments", "crm", "monitor"] as const), events: ["event"], subscribers: [], health: rng.weighted([["ok", 90], ["degraded", 7], ["down", 3]] as const), scopes: ["read"], retentionDays: 365, personalData: rng.chance(0.3), lastEventAt: iso(SEED_NOW - rng.int(0, 3600) * 1000), eventsPerHour: rng.int(1, 500) });
  for (let i = 0; i < 80; i++) d.templates.push({ id: `stpl-${i}`, tenantId, clusterId: active[i % active.length].id, name: `Template ${i}`, fields: [{ key: "f", label: "Field", sensors: [], required: true, freshnessHours: 24, value: "1", filledAt: iso(SEED_NOW - rng.int(0, 48) * HOUR), filledBy: `sa-${i}`, source: "generated" }], cadence: "Daily", owner: `sh-${i % 3}`, assignedAgents: [`sa-${i}`], freshnessRule: "Daily", requiredEvidence: [], status: rng.weighted([["complete", 70], ["partial", 20], ["stale", 10]] as const) });
  for (let i = 0; i < 30; i++) d.accessRules.push({ id: `sr-${i}`, tenantId, name: `Access rule ${i}`, appliesTo: `tool:t${i}`, requiresRoles: [], requiresAttributes: {}, requiresCapability: `cap:${i}`, sensitivity: rng.pick(["internal", "confidential", "restricted"] as const), description: "Generated rule." });
  d.resolver = d.skills.slice(0, 400).map((s, i) => ({ id: `rr-${s.id}`, tenantId, event: s.trigger, match: s.name.toLowerCase(), skill: { id: s.id, version: s.version, branch: "main" }, agentId: s.agentIds[0] ?? "sa-0", priority: i, triggerEval: { cases: 30, passRate: 0.8 + rng.float() * 0.2, lastRunAt: iso(SEED_NOW - DAY) } }));

  // Graph with about 2,400 nodes
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const push = (type: GraphNode["type"], id: string, label: string, clusterId: string, sensitivity: Sensitivity, cap: string | null = null) => {
    const ci = Math.max(0, d.clusters.findIndex((c) => c.id === clusterId));
    const a = (ci / 6) * Math.PI * 2 + rng.float() * 0.9;
    const r = 60 + rng.float() * 140;
    nodes.push({ id, type, label, refId: id, clusterId, sensitivity, requires: { capability: cap, roles: [] }, x: Math.cos(a) * r, y: Math.sin(a) * r });
  };
  d.agents.forEach((a) => push("agent", `n:${a.id}`, a.name, a.clusterId, "internal"));
  d.skills.forEach((s) => push("skill", `n:skill:${s.id}`, s.name, s.clusterId, "internal"));
  for (let i = 0; i < 60; i++) push("tool", `n:tool:t${i}`, `tool ${i}`, active[i % active.length].id, rng.pick(["internal", "confidential"] as const), `cap:${i}`);
  d.policies.forEach((p) => push("policy", `n:policy:${p.key}`, p.name, p.clusterId, "internal"));
  d.accessRules.forEach((r) => push("security", `n:sec:${r.id}`, r.name, active[0].id, r.sensitivity));
  d.facts.forEach((f) => push("fact", `n:fact:${f.id}`, f.statement, f.clusterId, f.sensitivity));
  d.documents.forEach((x) => push("document", `n:doc:${x.id}`, x.title, x.clusterId, x.sensitivity));
  d.templates.forEach((t) => push("template", `n:tpl:${t.id}`, t.name, t.clusterId, "internal"));
  d.sensors.forEach((s) => push("sensor", `n:sensor:${s.id}`, s.name, s.clusterId, "internal"));
  const add = (source: string, target: string, kind: GraphEdge["kind"], cap: string | null = null) => edges.push({ id: `e${edges.length}`, source, target, kind, requiresCapability: cap });
  d.agents.forEach((a) => a.skills.forEach((s) => add(`n:${a.id}`, `n:skill:${s.id}`, "uses")));
  d.skills.forEach((s, i) => { add(`n:skill:${s.id}`, `n:tool:t${i % 60}`, "uses", `cap:${i % 60}`); add(`n:policy:pol-${i % 60}`, `n:skill:${s.id}`, "governs"); add(`n:skill:${s.id}`, `n:tpl:stpl-${i % 80}`, "fills"); });
  d.facts.forEach((f, i) => add(`n:doc:sd-${i % 400}`, `n:fact:${f.id}`, "evidences"));
  d.sensors.forEach((s, i) => add(`n:sensor:${s.id}`, `n:sa-${i}`, "feeds"));
  d.graph = { nodes, edges };

  generateRuns(d, rng, 0.05, 14);
  generateAccessDecisions(d, rng, 3000);
  d.branches = [{ id: "br-main", tenantId, name: "main", env: "production", base: null, head: "s0", status: "protected", description: "Production", createdBy: { kind: "system", id: "system", name: "Brain" }, createdAt: iso(SEED_NOW - 400 * DAY) }];
  for (let i = 0; i < 300; i++) d.commits.push({ id: `s${i.toString(16)}`, tenantId, branch: "main", parentId: i ? `s${(i - 1).toString(16)}` : null, author: { kind: "agent", id: "sa-0", name: "Quality Supervisor" }, message: `Generated change ${i}`, changes: [{ op: "modify", nodeType: "skill", nodeId: `sk-${i}`, label: `skill ${i}`, field: "steps", before: "v1", after: "v2" }], criticality: rng.pick([0, 1, 2, 3] as const), evidence: [], createdAt: iso(SEED_NOW - (300 - i) * 3 * HOUR), tag: null });
  for (let i = 0; i < 60; i++) {
    const crit = rng.pick([2, 3, 4] as const);
    d.changeRequests.push({ id: `scr-${i}`, tenantId, title: `Generated change request ${i}`, kind: "skill", fromBranch: `sandbox/gen-${i}`, toBranch: "main", commits: [], plainDiff: [`Change ${i}`], changes: [], impactPreview: { runsReplayed: 500, decisionsChanged: rng.int(0, 40), predictedRisk: "low", summary: "Generated", examples: [] }, tests: null, approvalId: `sapr-${i}`, status: "awaiting_approval", criticality: crit, criticalityReasons: [], drafter: { kind: "agent", id: "sa-0", name: "Supervisor" }, dri: "sh-0", clusters: [active[i % active.length].id], createdAt: iso(SEED_NOW - rng.int(1, 72) * HOUR), mergedAt: null, coolingUntil: null, correlationId: `scr-${i}` });
    d.approvals.push({ id: `sapr-${i}`, tenantId, subject: { kind: "change_request", id: `scr-${i}` }, title: `Generated change request ${i}`, summary: "Generated for scale", criticality: crit, requiredApprovers: { tier: crit >= 3 ? "L1" : "L2", count: crit === 4 ? 2 : 1, roles: [] }, votes: [], dueAt: iso(SEED_NOW + rng.int(1, 96) * HOUR), createdAt: iso(SEED_NOW - rng.int(1, 72) * HOUR), status: "pending", delegatedTo: null, dri: "sh-0", drafter: { kind: "agent", id: "sa-0", name: "Supervisor" }, evidence: [], correlationId: `scr-${i}` });
  }
  for (let i = 0; i < 30; i++) {
    const dueAt = iso(SEED_NOW + rng.int(3, 90) * DAY);
    const items = [{ key: "a", label: "Evidence A", satisfiedBy: rng.chance(0.6) ? "x" : null }, { key: "b", label: "Evidence B", satisfiedBy: rng.chance(0.6) ? "x" : null }];
    const readiness = readinessOf(items);
    d.obligations.push({ id: `sob-${i}`, tenantId, clusterId: active[i % active.length].id, title: `Obligation ${i}`, jurisdiction: "Generated", category: rng.pick(["tax", "statutory", "contract", "renewal"] as const), dueAt, prepareBy: dueAt, requiredEvidence: items, readiness, status: statusOf(readiness, dueAt, SEED_NOW), dri: "sh-1", isSample: true, note: "Generated" });
  }
  d.loops = active.map((c, i) => ({ id: `sl-${i}`, tenantId, clusterId: c.id, name: `${c.name} loop`, description: "Generated loop", stages: (["sensor", "policy", "tool", "gate", "learning"] as const).map((key) => ({ key, label: key, refs: [], metric: { label: "rate", value: `${rng.int(60, 99)}%`, trend: 0 }, pending: rng.int(0, 3) })), runs7d: rng.int(1000, 9000), successRate: 0.8 + rng.float() * 0.18, autonomyRate: 0.6 + rng.float() * 0.3, history: [], experiments: [], dri: "sh-0" }));
  d.audit = d.runs.slice(0, 3000).map((r, i) => ({ id: `sau-${i}`, tenantId, at: r.startedAt, actor: { kind: "agent", id: r.agentId, name: r.agentId }, action: `run.${r.status}`, target: { type: "run", id: r.id, label: r.subject }, env: "production", criticality: 0, detail: "", correlationId: null }));
  runOvernightReview(d, { now: SEED_NOW - 7.5 * HOUR, actor: { kind: "agent", id: "sa-0", name: "Quality Supervisor" } });
  seedTrends(d, rng, "sh-0");
  seedMemory(d);
  d.activities = active.flatMap((c) => roleNames.slice(0, 5).map((r, j) => ({ cluster: c.id, activity: `${r} work`, agent: d.agents.find((a) => a.clusterId === c.id)?.id ?? "sa-0", sensors: j % 2 ? ["ss-0"] : [], template: j % 3 ? "stpl-0" : "", criticality: "C1" })));
  d.studio = seedStudio(d);
  return d;
}

export type { Experiment, LibrarianItem, Policy };
