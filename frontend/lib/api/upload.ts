"use client";

// Uploading a document from Ask the Brain. The brain reads it, masks personal data, files it in the Library and makes
// it searchable, so the next question can be answered from it.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as C from "@/contracts";
import { reportError } from "@/lib/errors";
import { useUi } from "@/lib/store";
import { apiUpload } from "./client";

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
