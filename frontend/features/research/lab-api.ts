// The Research Lab's API client and hooks. The Lab runs only on the real backend (Finebase HQ) with RESEARCH_LAB=enabled;
// every other case answers with a LabUnavailable error the screens turn into a plain explanation.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { LabCasePage, LabExperiment, LabOptions, LabPack, LabPrereg, LabProgress, LabResults, type LabAudit, type LabHypothesis, type ResearchPaper } from "@/contracts/research";
import { config, realTenants } from "@/lib/flags";
import { currentPersonaId, useUi } from "@/lib/store";

export class LabError extends Error {
  constructor(message: string, readonly status: number, readonly body: Record<string, unknown> = {}) {
    super(message);
  }
}

/** Why the Lab cannot answer here, in words a person can act on. */
export function labUnavailable(): string | null {
  return realTenants.has(useUi.getState().tenantId) ? null : "The Lab runs on Finebase HQ. Switch tenant in the top bar to use it.";
}

async function call<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
  const offline = labUnavailable();
  if (offline) throw new LabError(offline, 0);
  const headers: Record<string, string> = { "x-persona": currentPersonaId() };
  if (!(init.body instanceof FormData)) headers["content-type"] = "application/json";  // a form sets its own boundary
  const res = await fetch(`${config.apiBaseUrl}/research${path}`, { ...init, headers }).catch(() => null);
  if (!res) throw new LabError("The backend does not answer. Start it, then try again.", 0);
  const body = await res.json().catch(() => ({}));
  if (res.status === 404 && path === "/status") throw new LabError("The Lab is switched off. Set RESEARCH_LAB=enabled in backend/.env and restart the API.", 404);
  if (!res.ok) throw new LabError(typeof body.error === "string" ? body.error.replaceAll("_", " ") : `${res.status}`, res.status, body);
  return schema.parse(body);
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

// --- Reads (keyed by tenant, so switching to Finebase HQ asks again)

function useKey(...parts: unknown[]) {
  const tenant = useUi((s) => s.tenantId);
  return ["lab", tenant, ...parts];
}

export const useLabStatus = () => useQuery({ queryKey: useKey("status"), queryFn: () => call("/status", z.object({ lab: z.string(), store: z.string() })), retry: false });
export const usePacks = () => useQuery({ queryKey: useKey("packs"), queryFn: () => call("/packs", z.array(LabPack)), retry: false });
export const usePreregs = () => useQuery({ queryKey: useKey("preregs"), queryFn: () => call("/preregistrations", z.array(LabPrereg)), retry: false });
export const useExperiments = () => useQuery({ queryKey: useKey("experiments"), queryFn: () => call("/experiments", z.array(LabExperiment)), retry: false });
export const useOptions = () => useQuery({ queryKey: useKey("options"), queryFn: () => call("/options", LabOptions), retry: false });
export const useExperiment = (id: string) =>
  useQuery({ queryKey: useKey("experiment", id), queryFn: () => call(`/experiments/${id}`, LabExperiment), retry: false });
export const useProgress = (id: string, live: boolean) =>
  useQuery({ queryKey: useKey("progress", id), queryFn: () => call(`/experiments/${id}/progress`, LabProgress), refetchInterval: live ? 2000 : false, retry: false });
export const useResults = (id: string | null) =>
  useQuery({ queryKey: useKey("results", id), queryFn: () => call(`/experiments/${id}/results`, LabResults), enabled: !!id, retry: false });
export const useCase = (id: string, condition: string | null, failedOnly: boolean, offset: number) =>
  useQuery({
    queryKey: useKey("cases", id, condition, failedOnly, offset),
    queryFn: () => call(`/experiments/${id}/cases?${new URLSearchParams({ offset: String(offset), limit: "1", failed: String(failedOnly), ...(condition ? { condition } : {}) })}`, LabCasePage),
    retry: false,
  });

// --- Changes

export type UploadAnswer = { kept: true; created: boolean; pack: LabPack } | { kept: false; error: string; audits: LabAudit[]; needs: string[] };

export function useUploadPack() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, reasons }: { file: File; reasons: Record<string, string> }): Promise<UploadAnswer> => {
      const form = new FormData();
      form.append("file", file);
      form.append("reasons", JSON.stringify(reasons));
      try {
        const answer = await call("/packs", z.object({ pack: LabPack, created: z.boolean() }), { method: "POST", body: form });
        return { kept: true, created: answer.created, pack: answer.pack };
      } catch (error) {
        if (error instanceof LabError && (error.status === 422 || error.status === 409)) {
          return { kept: false, error: String(error.body.error), audits: (error.body.audits as LabAudit[]) ?? [], needs: (error.body.needs as string[]) ?? [] };
        }
        throw error;
      }
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["lab"] }),
  });
}

export function useCreatePrereg() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (draft: { paper: ResearchPaper; title: string; hypotheses: LabHypothesis[] }) => call("/preregistrations", LabPrereg, post(draft)),
    onSuccess: () => client.invalidateQueries({ queryKey: ["lab"] }),
  });
}

export function useLockPrereg() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, confirm }: { id: string; confirm: string }) => call(`/preregistrations/${id}/lock`, LabPrereg, post({ confirm })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["lab"] }),
  });
}

export function useCreateExperiment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { paper: ResearchPaper; packId: string; preregId: string; conditions: string[]; seeds: number[]; trials: number; model: string; budgetUsd: number }) =>
      call("/experiments", LabExperiment, post(body)),
    onSuccess: () => client.invalidateQueries({ queryKey: ["lab"] }),
  });
}

export function useStartExperiment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => call(`/experiments/${id}/start`, z.object({ started: z.boolean() }), { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["lab"] }),
  });
}

/** The problems a 422 named, for showing as a list. */
export function problemsOf(error: unknown): string[] {
  return error instanceof LabError && Array.isArray(error.body.problems) ? (error.body.problems as string[]) : error instanceof Error ? [error.message] : [String(error)];
}
