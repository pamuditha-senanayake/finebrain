"use client";

import { Paperclip } from "lucide-react";
import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { UPLOAD_TYPES } from "@/lib/api/upload";
import { attach } from "@/lib/voice/agent";

/** A paperclip that adds a document through the chat: Lisena reads it and asks what is missing before it is filed. */
export function AskUpload() {
  const picker = useRef<HTMLInputElement>(null);
  return (
    <>
      <input ref={picker} type="file" accept={UPLOAD_TYPES} className="hidden" aria-label="Document to add" onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) void attach(file); }} />
      <Button type="button" variant="ghost" size="icon" className="rounded-full text-muted-foreground" onClick={() => picker.current?.click()} aria-label="Add a document" title="Add a document">
        <Paperclip />
      </Button>
    </>
  );
}
