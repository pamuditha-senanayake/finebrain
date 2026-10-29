// Generates docs/openapi.json from the zod contracts, the single source of truth for every shape.
import { writeFileSync } from "node:fs";
import { z } from "zod";
import * as C from "../contracts";
import { ResearchSnapshot } from "../contracts/research";

const list = (s: z.ZodType) => z.array(s);
const resources: Record<string, z.ZodType> = {
  tenant: C.Tenant, clusters: list(C.Cluster), humans: list(C.Human), agents: list(C.Agent), "agents/{id}": C.Agent,
  skills: list(C.Skill), "skills/{id}": list(C.Skill), policies: list(C.Policy), "policies/{key}": list(C.Policy), facts: list(C.Fact),
  documents: list(C.Document), "filing-rules": list(C.FilingRule), "access-rules": list(C.AccessRule), sensors: list(C.Sensor),
  "tracking-plan": list(C.TrackingPlanItem), templates: list(C.Template), resolver: list(C.ResolverRule), graph: C.Graph,
  librarian: list(C.LibrarianItem), runs: list(C.Run), "runs/{id}": C.RunDetail, conversations: list(C.Conversation),
  "conversations/{id}": C.Conversation, escalations: list(C.Run), "access-decisions": list(C.AccessDecision), branches: list(C.Branch),
  commits: list(C.Commit), "change-requests": list(C.ChangeRequest), "change-requests/{id}": C.ChangeRequest, approvals: list(C.Approval),
  "approvals/{id}": C.Approval, obligations: list(C.Obligation), "evidence-requests": list(C.EvidenceRequest), grants: list(C.Grant),
  risks: list(C.Risk), "readiness-rules": list(C.ReadinessRule), gaps: list(C.ReadinessGap), loops: list(C.Loop), "loops/{id}": C.Loop,
  experiments: list(C.Experiment), audit: list(C.AuditEvent), notifications: list(C.Notification), digest: C.Digest.nullable(),
  overview: C.Overview, analytics: C.Analytics, search: list(C.SearchHit), research: list(ResearchSnapshot),
  activities: list(z.object({ cluster: z.string(), activity: z.string(), agent: z.string(), sensors: z.array(z.string()) })), clock: z.object({ now: z.string() }),
  // Workflow Studio
  "studio/map": C.BrainMap, "studio/workflows": list(C.WorkflowSummary), "studio/workflows/{id}": C.WorkflowDetail,
  "studio/workflows/{id}/health": z.object({ findings: z.array(C.Finding), fixes: z.array(C.Suggestion) }),
  "studio/tools": list(z.object({ tool: C.StudioItem, workflows: z.array(z.object({ id: z.string(), name: z.string() })) })),
  "studio/revisions": list(C.Revision), "studio/pending": list(C.PendingChange),
};
const ops = ["takeover", "handback", "sendMessage", "closeConversation", "skillify", "runChecks", "decide", "rollback", "runReadinessScheduler", "uploadEvidence", "requestGrant", "revokeGrant", "librarianPropose", "experimentPreview", "experimentStart", "experimentConclude", "experimentKeep", "experimentDiscard", "runOvernightReview", "saveSkillDraft", "promoteAgent", "revealPersonal", "addTrackingItem", "markRead", "studioApply", "studioSuggest"];

const json = (s: z.ZodType) => z.toJSONSchema(s, { unrepresentable: "any" });
const paths: Record<string, unknown> = {
  "/api/tenants": { get: { summary: "Tenants the user may open", responses: { 200: { description: "OK", content: { "application/json": { schema: { type: "array" } } } } } } },
};
for (const [path, schema] of Object.entries(resources)) {
  const params = [...path.matchAll(/\{(\w+)\}/g)].map((m) => ({ name: m[1], in: "path", required: true, schema: { type: "string" } }));
  paths[`/api/t/{tenant}/${path}`] = { get: { parameters: [{ name: "tenant", in: "path", required: true, schema: { type: "string" } }, ...params], responses: { 200: { description: "OK", content: { "application/json": { schema: json(schema) } } } } } };
}
for (const op of ops) paths[`/api/t/{tenant}/ops/${op}`] = { post: { summary: `Domain operation ${op}. Reference behaviour: lib/mock/ops.ts`, parameters: [{ name: "tenant", in: "path", required: true, schema: { type: "string" } }, { name: "x-persona", in: "header", schema: { type: "string" } }], requestBody: { content: { "application/json": { schema: { type: "object" } } } }, responses: { 200: { description: "OK" }, 403: { description: "Not allowed, with { error }" }, 409: { description: "Conflict, with { error }" } } } };
const askBody = z.object({ question: z.string(), page: z.object({ path: z.string(), scope: z.enum(["page", "system"]) }).optional() });
paths["/api/t/{tenant}/ask"] = { post: { requestBody: { content: { "application/json": { schema: json(askBody) } } }, responses: { 200: { description: "OK", content: { "application/json": { schema: json(C.AskAnswer) } } } } } };
// Studio assistant: replies are reads. Nothing changes until a proposal is confirmed through ops/studioApply.
const studioPosts: Record<string, [z.ZodType, z.ZodType]> = {
  "studio/chat": [C.ChatRequest, C.ChatReply],
  "studio/review": [z.object({ input: C.ProposalInput, workflowId: z.string() }), C.ChatReply],
};
for (const [path, [req, res]] of Object.entries(studioPosts)) paths[`/api/t/{tenant}/${path}`] = { post: { parameters: [{ name: "tenant", in: "path", required: true, schema: { type: "string" } }, { name: "x-persona", in: "header", schema: { type: "string" } }], requestBody: { content: { "application/json": { schema: json(req) } } }, responses: { 200: { description: "OK", content: { "application/json": { schema: json(res) } } } } } };
paths["/api/t/{tenant}/stream"] = { get: { summary: "Server Sent Events. Each message is a LiveEvent: { type, tenantId, at, resources[], summary }", responses: { 200: { description: "text/event-stream" } } } };

writeFileSync("docs/openapi.json", JSON.stringify({ openapi: "3.1.0", info: { title: "FineBrain API", version: "0.1.0", description: "Generated from contracts/ by npm run openapi." }, paths }, null, 2));
console.log(`docs/openapi.json: ${Object.keys(paths).length} paths`);
