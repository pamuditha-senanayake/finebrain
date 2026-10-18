"use client";

import { Loader2, Paperclip } from "lucide-react";
import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { UPLOAD_TYPES, useUploadDocument } from "@/lib/api/upload";

/** A paperclip that sends one document to the brain. It reports back in a short sentence. */
export function AskUpload({ onDone }: { onDone: (message: string, ok: boolean) => void }) {
  const picker = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();

  async function send(file: File | undefined) {
    if (!file) return;
    try {
      const doc = await upload.mutateAsync(file);
      onDone(`Added "${doc.title}" to the Library, sir. You can ask me about it now.`, true);
    } catch (e) {
      const reason = e instanceof Error ? e.message : "";
      onDone(reason.startsWith("unsupported_type") ? "I can read text, Markdown, CSV, PDF and Word files, sir." : reason === "too_large" ? "That file is over 10 MB, sir." : "I could not read that file, sir.", false);
    } finally {
      if (picker.current) picker.current.value = "";
    }
  }

  return (
    <>
      <input ref={picker} type="file" accept={UPLOAD_TYPES} className="hidden" onChange={(e) => void send(e.target.files?.[0])} aria-label="Document to upload" />
      <Button type="button" variant="ghost" size="icon" className="rounded-full text-muted-foreground" onClick={() => picker.current?.click()} disabled={upload.isPending} aria-label="Upload a document">
        {upload.isPending ? <Loader2 className="animate-spin" /> : <Paperclip />}
      </Button>
    </>
  );
}
