"use client";

// Uploading a document from Lisena. The brain reads it, masks personal data, files it in the Library and makes
// it searchable, so the next question can be answered from it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as C from "@/contracts";
import { reportError } from "@/lib/errors";
import { useUi } from "@/lib/store";
import { apiGet, apiPost, apiUpload } from "./client";

export const UPLOAD_TYPES = ".txt,.md,.csv,.pdf,.docx";

export function useUploadDocument() {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiUpload("documents", form, C.Document);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["t", tenantId, "documents"] }),
    onError: (e) => reportError(e, { op: "documents.upload" }),
  });
}

/** Step 16: a file uploaded to answer an evidence request. Its facts wait in the Vault; accepting one closes the gap. */
export function useUploadEvidence() {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  return useMutation({
    mutationFn: ({ requestId, file }: { requestId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      return apiUpload(`evidence-requests/${requestId}/upload`, form, C.Document);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["t", tenantId] }),
    onError: (e) => reportError(e, { op: "evidence.upload" }),
  });
}

// --- The guided intake: every document says what it is before it joins the knowledge base (backend intake.py)

/** Step 1: the file goes up; the brain fills what the text answers and lists the questions still open. */
export function useStartIntake() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiUpload("intake", form, C.IntakeDraft);
    },
    onError: (e) => reportError(e, { op: "intake.start" }),
  });
}

/** Step 2: one or more answers; bad ones are not kept, so the next question comes back. */
export function useAnswerIntake() {
  return useMutation({
    mutationFn: ({ intakeId, fields }: { intakeId: string; fields: Record<string, unknown> }) => apiPost(`intake/${intakeId}/answer`, { fields }, C.IntakeDraft),
  });
}

/** Step 3: filed only when every required field is known; a second click files nothing twice. */
export function useFileIntake() {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  return useMutation({
    mutationFn: (intakeId: string) => apiPost(`intake/${intakeId}/file`, {}, C.Document),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["t", tenantId, "documents"] }),
    onError: (e) => reportError(e, { op: "intake.file" }),
  });
}

/** The rules every document is checked against, as the backend holds them. */
export function useIntakeRules(enabled: boolean) {
  const tenantId = useUi((s) => s.tenantId);
  return useQuery({ queryKey: ["t", tenantId, "intake-rules"], queryFn: ({ signal }) => apiGet("intake/policy", C.IntakeRules, signal), enabled, staleTime: Infinity });
}

/** Off: kept, but no answer or agent reads it. On: it answers again. */
export function useSwitchDocument() {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  return useMutation({
    mutationFn: ({ id, on }: { id: string; on: boolean }) => apiPost(`documents/${id}/switch`, { on }, C.Document),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["t", tenantId, "documents"] }),
    onError: (e) => reportError(e, { op: "documents.switch" }),
  });
}
