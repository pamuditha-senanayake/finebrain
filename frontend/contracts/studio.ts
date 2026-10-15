import { z } from "zod";
import { Criticality, IsoDate } from "./common";

// Workflow Studio. A workflow owns its skills, agents, policies, templates, sensors, schedulers and loops.
// Tools are the one shared layer: they live outside any workflow and many workflows can use the same tool.

export const MemberKind = z.enum(["skill", "agent", "policy", "template", "sensor", "scheduler", "loop", "tool"]);
export type MemberKind = z.infer<typeof MemberKind>;

export const StudioKind = z.enum(["workflow", ...MemberKind.options]);
export type StudioKind = z.infer<typeof StudioKind>;

export const ItemStatus = z.enum(["active", "draft", "paused", "retired"]);
export type ItemStatus = z.infer<typeof ItemStatus>;

export const FieldValue = z.union([z.string(), z.number(), z.boolean(), z.array(z.string())]);
export type FieldValue = z.infer<typeof FieldValue>;

/** Kind specific settings. Which keys exist for which kind is described by FIELD_SPECS in lib/studio/spec.ts. */
export const ItemFields = z.record(z.string(), FieldValue);
export type ItemFields = z.infer<typeof ItemFields>;

export const StudioItem = z.object({
  id: z.string(),
  kind: MemberKind,
  workflowId: z.string().nullable().describe("null for tools, which are shared"),
  name: z.string(),
  description: z.string(),
  topics: z.array(z.string()),
  status: ItemStatus,
  version: z.number().int(),
  dri: z.string(),
  fields: ItemFields,
  updatedAt: IsoDate,
  updatedBy: z.string(),
});
export type StudioItem = z.infer<typeof StudioItem>;

/** One concrete example of the problem, written as a BDD scenario: what happens today, and what should happen instead. */
export const Scenario = z.object({
  id: z.string(),
  title: z.string(),
  given: z.array(z.string()),
  when: z.string(),
  then: z.array(z.string()).describe("What happens today, before the workflow"),
  goal: z.string().describe("What should happen once the workflow handles this case"),
  coveredBy: z.array(z.string()).describe("Parts of the workflow that handle this case"),
});
export type Scenario = z.infer<typeof Scenario>;

/** Why a workflow exists: the problem, how it is handled today, and the cases it must handle. */
export const Story = z.object({
  problem: z.string(),
  today: z.string(),
  scenarios: z.array(Scenario),
});
export type Story = z.infer<typeof Story>;

/** A story the chat drafted and is waiting for the person to confirm. Null workflowId means it starts a new workflow. */
export const StoryDraft = z.object({
  workflowId: z.string().nullable(),
  name: z.string(),
  story: Story,
});
export type StoryDraft = z.infer<typeof StoryDraft>;

export const Workflow = z.object({
  id: z.string(),
  tenantId: z.string(),
  name: z.string(),
  description: z.string(),
  topics: z.array(z.string()),
  status: ItemStatus,
  version: z.number().int(),
  clusterId: z.string(),
  dri: z.string(),
  editors: z.array(z.string()).describe("People besides the DRI who may confirm low criticality edits"),
  criticality: Criticality,
  members: z.array(z.string()),
  story: Story.nullable().default(null),
  updatedAt: IsoDate,
  updatedBy: z.string(),
});
export type Workflow = z.infer<typeof Workflow>;

export const WorkflowSummary = Workflow.extend({
  counts: z.record(MemberKind, z.number().int()),
  health: z.object({ breaks: z.number().int(), warnings: z.number().int() }),
  pending: z.number().int(),
});
export type WorkflowSummary = z.infer<typeof WorkflowSummary>;

export const WorkflowDetail = z.object({
  workflow: Workflow,
  items: z.array(StudioItem).describe("The workflow's own members plus every shared tool it uses"),
  sharedToolUse: z.array(z.object({ toolId: z.string(), workflows: z.array(z.object({ id: z.string(), name: z.string() })) })),
});
export type WorkflowDetail = z.infer<typeof WorkflowDetail>;

export const Snapshot = z.object({
  name: z.string(),
  description: z.string(),
  topics: z.array(z.string()),
  status: ItemStatus,
  fields: ItemFields,
});
export type Snapshot = z.infer<typeof Snapshot>;

export const Verdict = z.enum(["minimal", "moderate", "breaking"]);
export type Verdict = z.infer<typeof Verdict>;

export const Revision = z.object({
  id: z.string(),
  targetKind: StudioKind,
  targetId: z.string(),
  workflowId: z.string().nullable(),
  version: z.number().int(),
  op: z.enum(["create", "update", "delete"]),
  at: IsoDate,
  by: z.string(),
  summary: z.string(),
  snapshot: Snapshot.nullable().describe("State after this revision; null after a delete"),
  verdict: Verdict.nullable(),
  changeRequestId: z.string().nullable(),
});
export type Revision = z.infer<typeof Revision>;

export const FieldChange = z.object({
  field: z.string(),
  label: z.string(),
  before: z.string().nullable(),
  after: z.string().nullable(),
});
export type FieldChange = z.infer<typeof FieldChange>;

/** What a person (through the chat or a form) asks to change. The mock server rebuilds the full proposal from this, so nothing the browser claims about impact is trusted. */
export const ProposalInput = z.object({
  intent: z.enum(["create", "update", "delete"]),
  kind: StudioKind,
  targetId: z.string().nullable(),
  workflowId: z.string().nullable(),
  patch: z.object({
    name: z.string().optional(),
    description: z.string().optional(),
    topics: z.array(z.string()).optional(),
    status: ItemStatus.optional(),
    dri: z.string().optional(),
    fields: ItemFields.optional(),
    story: Story.optional().describe("Workflows only: the problem and its scenarios"),
  }),
});
export type ProposalInput = z.infer<typeof ProposalInput>;

export const Suggestion = z.object({
  label: z.string(),
  prompt: z.string().describe("Sent as the next chat message when picked"),
  tone: z.enum(["primary", "neutral", "fix"]).default("neutral"),
  input: ProposalInput.optional().describe("When set, picking the suggestion reviews exactly this change instead of parsing the prompt"),
});
export type Suggestion = z.infer<typeof Suggestion>;

export const Finding = z.object({
  severity: z.enum(["info", "warn", "break"]),
  text: z.string(),
  ref: z.object({ kind: StudioKind, id: z.string() }).nullable(),
});
export type Finding = z.infer<typeof Finding>;

export const Review = z.object({
  reviewer: z.string(),
  verdict: Verdict,
  criticality: Criticality,
  criticalityReasons: z.array(z.string()),
  summary: z.string(),
  findings: z.array(Finding),
  affected: z.array(z.object({ kind: StudioKind, id: z.string(), name: z.string(), workflowId: z.string().nullable(), how: z.string() })),
  otherWorkflows: z.array(z.object({ id: z.string(), name: z.string(), via: z.string() })),
  fixes: z.array(Suggestion),
  authority: z.object({
    canApply: z.boolean(),
    route: z.enum(["apply", "approval", "view_only"]),
    approver: z.string(),
    reason: z.string(),
  }),
});
export type Review = z.infer<typeof Review>;

export const Proposal = z.object({
  input: ProposalInput,
  title: z.string(),
  targetName: z.string(),
  changes: z.array(FieldChange),
  review: Review,
});
export type Proposal = z.infer<typeof Proposal>;

export const StudioCard = z.object({
  id: z.string(),
  kind: StudioKind,
  targetId: z.string(),
  workflowId: z.string().nullable(),
  title: z.string(),
  subtitle: z.string(),
  body: z.string(),
  badges: z.array(z.string()),
  current: z.boolean(),
  at: IsoDate.nullable(),
});
export type StudioCard = z.infer<typeof StudioCard>;

export const ChatTurn = z.object({ role: z.enum(["user", "assistant"]), text: z.string() });

export const ChatRequest = z.object({
  workflowId: z.string(),
  message: z.string(),
  focus: z.object({ kind: StudioKind, id: z.string() }).nullable(),
  history: z.array(ChatTurn),
  story: StoryDraft.nullable().default(null).describe("The story under discussion, sent back so the person can confirm or change it"),
});
export type ChatRequest = z.infer<typeof ChatRequest>;

export const ChatReply = z.object({
  answer: z.string(),
  bullets: z.array(z.string()),
  cards: z.array(StudioCard),
  suggestions: z.array(Suggestion),
  proposal: Proposal.nullable(),
  focus: z.object({ kind: StudioKind, id: z.string() }).nullable(),
  workflowId: z.string().nullable().describe("Set when the reply moves the conversation to another workflow"),
  story: StoryDraft.nullable().default(null).describe("Set when the reply drafts a problem and its scenarios for the person to confirm"),
});
export type ChatReply = z.infer<typeof ChatReply>;

export const ApplyResult = z.object({
  status: z.enum(["applied", "routed"]),
  targetId: z.string(),
  revisionId: z.string().nullable(),
  changeRequestId: z.string().nullable(),
  message: z.string(),
});
export type ApplyResult = z.infer<typeof ApplyResult>;

export const PendingChange = z.object({
  id: z.string(),
  changeRequestId: z.string(),
  workflowId: z.string().nullable(),
  input: ProposalInput,
  title: z.string(),
  verdict: Verdict,
  criticality: Criticality,
  by: z.string(),
  at: IsoDate,
  status: z.enum(["awaiting_approval", "applied", "rejected"]),
});
export type PendingChange = z.infer<typeof PendingChange>;

/** Everything the L1 brain map draws: clusters, their workflows, and each workflow's parts. */
export const BrainMap = z.object({
  clusters: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      description: z.string(),
      status: z.enum(["active", "planned"]),
      dri: z.string().nullable(),
      health: z.number(),
      kpi: z.object({ runs24h: z.number().int(), autonomyRate: z.number(), escalationRate: z.number(), costPerResolvedUsd: z.number(), moneyAtStakeMinor: z.number().int(), openRisks: z.number().int() }).nullable(),
    }),
  ),
  workflows: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      description: z.string(),
      clusterId: z.string(),
      status: ItemStatus,
      criticality: Criticality,
      dri: z.string(),
      health: z.object({ breaks: z.number().int(), warnings: z.number().int() }),
      items: z.array(z.object({ id: z.string(), kind: MemberKind, name: z.string(), description: z.string(), status: ItemStatus, shared: z.boolean() })),
    }),
  ),
});
export type BrainMap = z.infer<typeof BrainMap>;
