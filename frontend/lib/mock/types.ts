import type {
  AccessDecision,
  AccessRule,
  Agent,
  Approval,
  AuditEvent,
  Branch,
  ChangeRequest,
  Cluster,
  Commit,
  Conversation,
  Digest,
  Document,
  EvidenceRequest,
  Experiment,
  Fact,
  FilingRule,
  Grant,
  Graph,
  Human,
  LibrarianItem,
  Loop,
  Notification,
  Obligation,
  PendingChange,
  Revision,
  StudioItem,
  Workflow,
  Policy,
  ReadinessGap,
  ReadinessRule,
  ResolverRule,
  Risk,
  Run,
  Sensor,
  Skill,
  Template,
  Tenant,
  TrackingPlanItem,
  TraceStep,
  TrendCard,
  DriftItem,
  ExtractedSkill,
  Pattern,
  TraceSummary,
} from "@/contracts";

export type ActivityDef = {
  cluster: string;
  activity: string;
  agent: string;
  sensors: string[];
  template: string;
  criticality: string;
};

export type StudioData = {
  workflows: Workflow[];
  items: StudioItem[];
  revisions: Revision[];
  pending: PendingChange[];
};

// Living memory: traces newest first, their patterns, drift and skill drafts (seed/memory.ts).
export type MemoryData = {
  traces: TraceSummary[];
  patterns: Pattern[];
  drifts: DriftItem[];
  skills: ExtractedSkill[];
};

export type TenantData = {
  tenant: Tenant;
  clusters: Cluster[];
  humans: Human[];
  agents: Agent[];
  activities: ActivityDef[];
  skills: Skill[];
  policies: Policy[];
  facts: Fact[];
  documents: Document[];
  filingRules: FilingRule[];
  accessRules: AccessRule[];
  sensors: Sensor[];
  trackingPlan: TrackingPlanItem[];
  templates: Template[];
  resolver: ResolverRule[];
  graph: Graph;
  librarian: LibrarianItem[];
  runs: Run[];
  specialSteps: Record<string, TraceStep[]>;
  conversations: Conversation[];
  accessDecisions: AccessDecision[];
  branches: Branch[];
  commits: Commit[];
  changeRequests: ChangeRequest[];
  approvals: Approval[];
  obligations: Obligation[];
  evidenceRequests: EvidenceRequest[];
  grants: Grant[];
  risks: Risk[];
  readinessRules: ReadinessRule[];
  gaps: ReadinessGap[];
  loops: Loop[];
  experiments: Experiment[];
  audit: AuditEvent[];
  notifications: Notification[];
  digest: Digest | null;
  trends: TrendCard[];
  memory: MemoryData;
  studio: StudioData;
  counter: number;
};
