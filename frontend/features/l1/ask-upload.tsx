"use client";

import { Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { openAddDocument } from "@/features/l2/add-document";

/** A paperclip that opens the guided intake, so every document says what it is before it is filed. */
export function AskUpload() {
  return (
    <Button type="button" variant="ghost" size="icon" className="rounded-full text-muted-foreground" onClick={openAddDocument} aria-label="Add a document" title="Add a document">
      <Paperclip />
    </Button>
  );
}
