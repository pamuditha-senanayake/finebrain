"use client";

// row-menu.tsx: the "..." on a connection row: Rename and Delete. Delete asks once before it erases the connection and its keys.
// Used by: hub.tsx. Uses: lib/api/connections.ts.
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { deleteConnection, renameConnection, useConnectionAction } from "@/lib/api/connections";

export function RowMenu({ id, name }: { id: string; name: string }) {
  const [mode, setMode] = useState<"rename" | "delete" | null>(null);
  const [draft, setDraft] = useState(name);
  const rename = useConnectionAction(renameConnection);
  const remove = useConnectionAction(deleteConnection);
  const close = () => setMode(null);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={`${name} options`}><MoreHorizontal /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => { setDraft(name); setMode("rename"); }}><Pencil /> Rename</DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => setMode("delete")}><Trash2 /> Delete</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={mode === "rename"} onOpenChange={(open) => !open && close()}>
        <DialogContent>
          <DialogTitle>Rename</DialogTitle>
          <Input value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Name" autoFocus />
          <DialogFooter>
            <Button variant="ghost" onClick={close}>Cancel</Button>
            <Button disabled={!draft.trim() || rename.isPending} onClick={() => rename.mutate({ id, name: draft.trim() }, { onSuccess: close })}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={mode === "delete"} onOpenChange={(open) => !open && close()}>
        <DialogContent>
          <DialogTitle>Delete {name}?</DialogTitle>
          <DialogDescription>Its keys are erased too. This cannot be undone.</DialogDescription>
          <DialogFooter>
            <Button variant="ghost" onClick={close}>Cancel</Button>
            <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate(id, { onSuccess: close })}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
