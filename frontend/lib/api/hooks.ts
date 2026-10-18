"use client";

import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import * as C from "@/contracts";
import { ResearchSnapshot } from "@/contracts/research";
import { reportError } from "@/lib/errors";
import { useUi } from "@/lib/store";
import { apiGet, apiGlobal, apiPost } from "./client";

export function useTenantId() {
  return useUi((s) => s.tenantId);
}

function useResource<T>(path: string, schema: z.ZodType<T>, opts: Partial<UseQueryOptions<T>> = {}) {
  const tenantId = useTenantId();
  const resource = path.split("?")[0].split("/")[0];
  return useQuery<T>({
    queryKey: ["t", tenantId, resource, path],
    queryFn: ({ signal }) => apiGet(path, schema, signal),
    ...opts,
  });
}

const list = <T extends z.ZodTypeAny>(s: T) => z.array(s);

export const useTenants = () => useQuery({ queryKey: ["tenants"], queryFn: () => apiGlobal("tenants", z.array(z.object({ id: z.string(), name: z.string(), isScaleDemo: z.boolean() }))) });
export const useTenant = () => useResource("tenant", C.Tenant);
export const useClusters = () => useResource("clusters", list(C.Cluster));
export const useHumans = () => useResource("humans", list(C.Human));
export const useAgents = () => useResource("agents", list(C.Agent));
export const useAgent = (id: string) => useResource(`agents/${id}`, C.Agent, { enabled: !!id });
export const useSkills = (branch?: string) => useResource(branch ? `skills?branch=${encodeURIComponent(branch)}` : "skills", list(C.Skill));
export const useSkillVersions = (id: string) => useResource(`skills/${id}`, list(C.Skill), { enabled: !!id });
export const usePolicies = () => useResource("policies", list(C.Policy));
export const usePolicyVersions = (key: string) => useResource(`policies/${key}`, list(C.Policy), { enabled: !!key });
export const useFacts = () => useResource("facts", list(C.Fact));
export const useDocuments = () => useResource("documents", list(C.Document));
export const useFilingRules = () => useResource("filing-rules", list(C.FilingRule));
export const useAccessRules = () => useResource("access-rules", list(C.AccessRule));
export const useSensors = () => useResource("sensors", list(C.Sensor));
export const useTrackingPlan = () => useResource("tracking-plan", list(C.TrackingPlanItem));
export const useTemplates = () => useResource("templates", list(C.Template));
export const useResolver = () => useResource("resolver", list(C.ResolverRule));
export const useGraph = () => useResource("graph", C.Graph, { staleTime: 60_000 });
export const useLibrarian = () => useResource("librarian", list(C.LibrarianItem));
export const useRuns = (params: { agentId?: string; status?: string; limit?: number } = {}) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString();
  return useResource(q ? `runs?${q}` : "runs", list(C.Run));
};
export const useRun = (id: string) => useResource(`runs/${id}`, C.RunDetail, { enabled: !!id });
export const useConversations = () => useResource("conversations", list(C.Conversation));
export const useConversation = (id: string) => useResource(`conversations/${id}`, C.Conversation, { enabled: !!id });
export const useEscalations = () => useResource("escalations", list(C.Run));
export const useAccessDecisions = (params: { principal?: string; decision?: string } = {}) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v).map(([k, v]) => [k, String(v)])).toString();
  return useResource(q ? `access-decisions?${q}` : "access-decisions", list(C.AccessDecision));
};
export const useBranches = () => useResource("branches", list(C.Branch));
export const useCommits = (branch?: string) => useResource(branch ? `commits?branch=${encodeURIComponent(branch)}` : "commits", list(C.Commit));
export const useChangeRequests = () => useResource("change-requests", list(C.ChangeRequest));
export const useChangeRequest = (id: string) => useResource(`change-requests/${id}`, C.ChangeRequest, { enabled: !!id });
export const useApprovals = () => useResource("approvals", list(C.Approval));
export const useApproval = (id: string) => useResource(`approvals/${id}`, C.Approval, { enabled: !!id });
export const useObligations = () => useResource("obligations", list(C.Obligation));
export const useEvidenceRequests = () => useResource("evidence-requests", list(C.EvidenceRequest));
export const useGrants = () => useResource("grants", list(C.Grant));
export const useRisks = () => useResource("risks", list(C.Risk));
export const useReadinessRules = () => useResource("readiness-rules", list(C.ReadinessRule));
export const useGaps = () => useResource("gaps", list(C.ReadinessGap));
export const useLoops = () => useResource("loops", list(C.Loop));
export const useLoop = (id: string) => useResource(`loops/${id}`, C.Loop, { enabled: !!id });
export const useExperiments = () => useResource("experiments", list(C.Experiment));
export const useAudit = (params: { correlation?: string; actor?: string; env?: string; minCriticality?: number } = {}) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)])).toString();
  return useResource(q ? `audit?${q}` : "audit", list(C.AuditEvent));
};
export const useNotifications = () => useResource("notifications", list(C.Notification));
export const useDigest = () => useResource("digest", C.Digest.nullable());
export const useOverview = () => useResource("overview", C.Overview);
export const useAnalytics = () => useResource("analytics", C.Analytics);
export const useTrends = () => useResource("trends", list(C.TrendCard));
export const useActivities = () => useResource("activities", list(z.object({ cluster: z.string(), activity: z.string(), agent: z.string(), sensors: z.array(z.string()), template: z.string(), criticality: z.string() })));
export const useSearch = (q: string) => useResource(`search?q=${encodeURIComponent(q)}`, list(C.SearchHit), { enabled: q.trim().length > 1 });
export const useResearch = () => useResource("research", list(ResearchSnapshot));
export const useBrainMap = () => useResource("studio/map", C.BrainMap);
export const useStudioWorkflows = () => useResource("studio/workflows", list(C.WorkflowSummary));
export const useStudioWorkflow = (id: string) => useResource(`studio/workflows/${id}`, C.WorkflowDetail, { enabled: !!id });
export const useStudioHealth = (id: string) => useResource(`studio/workflows/${id}/health`, z.object({ findings: z.array(C.Finding), fixes: z.array(C.Suggestion) }), { enabled: !!id });
export const useStudioHistory = (targetId: string) => useResource(`studio/revisions?target=${encodeURIComponent(targetId)}`, list(C.Revision), { enabled: !!targetId });
export const useStudioActivity = (workflowId: string) => useResource(`studio/revisions?workflow=${encodeURIComponent(workflowId)}`, list(C.Revision), { enabled: !!workflowId });
export const useStudioTools = () => useResource("studio/tools", list(z.object({ tool: C.StudioItem, workflows: z.array(z.object({ id: z.string(), name: z.string() })) })));
export const useStudioPending = () => useResource("studio/pending", list(C.PendingChange));

/** Studio assistant. Replies are reads; nothing changes until a proposal is confirmed through `studioApply`. */
export function useStudioChat() {
  return useMutation({
    mutationFn: (req: C.ChatRequest) => apiPost("studio/chat", req, C.ChatReply),
    onError: (e) => reportError(e, { op: "studio.chat" }),
  });
}

export function useStudioReview() {
  return useMutation({
    mutationFn: (body: { input: C.ProposalInput; workflowId: string }) => apiPost("studio/review", body, C.ChatReply),
    onError: (e) => reportError(e, { op: "studio.review" }),
  });
}

export const useClock = () => useResource("clock", z.object({ now: z.string() }), { refetchInterval: 60_000 });

/** The brain's clock (the mock clock in demos), so countdowns agree with the data. */
export function useNow() {
  const clock = useClock();
  const [fallback] = useState(() => Date.now());
  return clock.data ? Date.parse(clock.data.now) : fallback;
}

/** Calls a domain operation, then refreshes the tenant's data. */
export function useOp<A = Record<string, unknown>>(op: string, opts: { success?: string; silent?: boolean } = {}) {
  const qc = useQueryClient();
  const tenantId = useTenantId();
  return useMutation({
    mutationFn: (args: A) => apiPost(`ops/${op}`, args, z.unknown()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["t", tenantId] });
      if (opts.success) toast.success(opts.success);
    },
    onError: (e) => {
      reportError(e, { op });
      if (!opts.silent) toast.error(e instanceof Error ? e.message : "Action failed");
    },
  });
}

export function useAsk() {
  return useMutation({ mutationFn: (input: { question: string; page?: { path: string; scope: "page" | "system" } }) => apiPost("ask", input, C.AskAnswer) });
}
