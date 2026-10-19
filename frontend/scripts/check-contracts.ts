// check-contracts.ts: fetch every Finebase HQ resource the backend serves and parse it with the console's zod
// contracts, so a shape that drifts on either side shows up here. Run with the API up:  npx tsx scripts/check-contracts.ts
import { z } from "zod";
import * as C from "../contracts";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TENANT = "finebase-hq";
const PERSONA = "h-pamuditha";

const CHECKS: [string, z.ZodType][] = [
  ["tenant", C.Tenant],
  ["humans", z.array(C.Human)],
  ["clusters", z.array(C.Cluster)],
  ["runs", z.array(C.Run)],
  ["escalations", z.array(C.Run)],
  ["approvals", z.array(C.Approval)],
  ["access-decisions", z.array(C.AccessDecision)],
  ["audit", z.array(C.AuditEvent)],
  ["sensors", z.array(C.Sensor)],
  ["trends", z.array(C.TrendCard)],
  ["agents", z.array(C.Agent)],
  ["agents/agent_refund_worker", C.Agent],
  ["skills", z.array(C.Skill)],
  ["skills/skill_refund_handling", z.array(C.Skill)],
  ["policies", z.array(C.Policy)],
  ["policies/policy_refund", z.array(C.Policy)],
  ["resolver", z.array(C.ResolverRule)],
  ["graph", C.Graph],
  ["overview", C.Overview],
  ["studio/map", C.BrainMap],
  ["documents", z.array(C.Document)],
  ["filing-rules", z.array(C.FilingRule)],
  ["facts", z.array(C.Fact)],
  ["librarian", z.array(C.LibrarianItem)],
  ["obligations", z.array(C.Obligation)],
  ["readiness-rules", z.array(C.ReadinessRule)],
  ["risks", z.array(C.Risk)],
  ["gaps", z.array(C.ReadinessGap)],
  ["evidence-requests", z.array(C.EvidenceRequest)],
  ["grants", z.array(C.Grant)],
  ["lists/runs?limit=20", C.ListPage(C.Run)],
  ["lists/escalations", C.ListPage(C.Run)],
  ["lists/audit?limit=20", C.ListPage(C.AuditEvent)],
  ["lists/access-decisions?limit=20", C.ListPage(C.AccessDecision)],
  ["lists/documents", C.ListPage(C.Document)],
  ["search?q=refund", z.array(C.SearchHit)],
  ["studio/workflows", z.array(C.WorkflowSummary)],
  ["studio/workflows/wf_act_refund_request", C.WorkflowDetail],
  ["studio/workflows/wf_act_refund_request/health", z.object({ findings: z.array(C.Finding), fixes: z.array(C.Suggestion) })],
  ["studio/tools", z.array(z.object({ tool: C.StudioItem, workflows: z.array(z.object({ id: z.string(), name: z.string() })) }))],
  ["studio/revisions?workflow=wf_act_refund_request", z.array(C.Revision)],
  ["studio/pending", z.array(C.PendingChange)],
  ["notifications", z.array(C.Notification)],
  ["branches", z.array(C.Branch)],
  ["commits", z.array(C.Commit)],
  ["change-requests", z.array(C.ChangeRequest)],
];

async function fetchJson(path: string) {
  const res = await fetch(`${API}/api/t/${TENANT}/${path}`, { headers: { "x-persona": PERSONA } });
  return { status: res.status, body: await res.json() };
}

async function check(path: string, schema: z.ZodType): Promise<boolean> {
  const { status, body } = await fetchJson(path);
  const result = schema.safeParse(body);
  const size = Array.isArray(body) ? ` (${body.length})` : "";
  const issue = result.success ? "" : ` ${result.error.issues[0]?.path.join(".")}: ${result.error.issues[0]?.message}`;
  console.log(`${result.success && status === 200 ? "ok  " : "FAIL"} ${path}${size}${issue}`);
  return result.success && status === 200;
}

async function main() {
  // Lists first, then the first run and approval in detail
  const results = [];
  for (const [path, schema] of CHECKS) results.push(await check(path, schema));
  const runs = (await fetchJson("runs")).body as { id: string }[];
  if (runs[0]) results.push(await check(`runs/${runs[0].id}`, C.RunDetail));
  const approvals = (await fetchJson("approvals")).body as { id: string }[];
  if (approvals[0]) results.push(await check(`approvals/${approvals[0].id}`, C.Approval));
  // Studio: a review is a read; the check never applies a change
  const reviewed = await fetch(`${API}/api/t/${TENANT}/studio/review`, { method: "POST", headers: { "x-persona": PERSONA, "content-type": "application/json" }, body: JSON.stringify({ workflowId: "wf_act_refund_request", input: { intent: "update", kind: "policy", targetId: "policy_refund", workflowId: "wf_act_refund_request", patch: { fields: { "param.days": 45 } } } }) });
  const reply = C.ChatReply.safeParse(await reviewed.json());
  console.log(`${reply.success && reviewed.ok ? "ok  " : "FAIL"} studio/review${reply.success ? "" : ` ${reply.error.issues[0]?.path.join(".")}: ${reply.error.issues[0]?.message}`}`);
  results.push(reply.success && reviewed.ok);

  // Ask the Brain is a POST
  const asked = await fetch(`${API}/api/t/${TENANT}/ask`, { method: "POST", headers: { "x-persona": PERSONA, "content-type": "application/json" }, body: JSON.stringify({ question: "What is the refund window?", page: { path: "/l1/ask", scope: "system" } }) });
  const answer = C.AskAnswer.safeParse(await asked.json());
  console.log(`${answer.success && asked.ok ? "ok  " : "FAIL"} ask${answer.success ? "" : ` ${answer.error.issues[0]?.path.join(".")}: ${answer.error.issues[0]?.message}`}`);
  results.push(answer.success && asked.ok);
  if (answer.success && answer.data.conversationId) results.push(await check(`ask/turns?conversation=${answer.data.conversationId}`, z.array(C.AskTurn)));
  process.exit(results.every(Boolean) ? 0 : 1);
}

main();
