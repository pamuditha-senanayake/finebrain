"use client";

// tasks.tsx: A3, what people promised and whether it is done. Tasks come from meetings' action points (the "Meeting
// tasks" workflow) or are added by hand. Late and due soon come first; done ones wait behind a click. A task opens in a
// side sheet to change its name, owner or day. Used by: app/(l1)/l1/tasks/page.tsx. Uses: lib/api/tasks.ts.
import { ChevronRight, ListTodo, Plus } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { Task } from "@/contracts";
import { PageHeader, QueryView } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useAddTask, useChangeTask, useTasks } from "@/lib/api/tasks";
import { date } from "@/lib/format";
import { cn } from "@/lib/utils";

// Config
const GROUPS = [
  { state: "late", label: "Late", tone: "text-risk" },
  { state: "soon", label: "Due soon", tone: "text-warn-fg" },
  { state: "open", label: "Open", tone: "text-muted-foreground" },
] as const;
const EVERYONE = "";

export function TasksView() {
  const tasks = useTasks();
  const [owner, setOwner] = useState(EVERYONE);
  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [showDone, setShowDone] = useState(false);

  return (
    <div>
      <PageHeader title="Tasks" description="What people promised in meetings, until it is done." actions={<Button onClick={() => setAdding(true)}><Plus /> Add task</Button>} />
      <QueryView query={tasks}>
        {(all) => {
          if (all.length === 0) return <Empty onAdd={() => setAdding(true)} />;
          const owners = [...new Set(all.map((t) => t.owner))].sort();
          const mine = all.filter((t) => owner === EVERYONE || t.owner === owner);
          const done = mine.filter((t) => t.state === "done");
          const open = all.find((t) => t.id === openId) ?? null;
          return (
            <div className="space-y-8">
              <OwnerFilter owners={owners} value={owner} onChange={setOwner} />
              {GROUPS.map((g) => {
                const shown = mine.filter((t) => t.state === g.state);
                return shown.length > 0 && (
                  <section key={g.state} aria-labelledby={`tasks-${g.state}`}>
                    <h2 id={`tasks-${g.state}`} className={cn("mb-3 text-[15px] font-semibold", g.tone)}>{g.label} <span className="font-normal text-muted-foreground">{shown.length}</span></h2>
                    <TaskList tasks={shown} onOpen={setOpenId} />
                  </section>
                );
              })}
              {mine.every((t) => t.state === "done") && <p className="text-[15px] text-muted-foreground">Nothing open{owner ? ` for ${owner}` : ""}.</p>}
              {done.length > 0 && (
                <section>
                  <Button variant="ghost" className="-ml-3 text-muted-foreground" aria-expanded={showDone} onClick={() => setShowDone(!showDone)}>{showDone ? "Hide done" : `Show done (${done.length})`}</Button>
                  {showDone && <div className="mt-3"><TaskList tasks={done} onOpen={setOpenId} /></div>}
                </section>
              )}
              <TaskSheet task={open} onClose={() => setOpenId(null)} />
            </div>
          );
        }}
      </QueryView>
      <AddTask open={adding} onOpenChange={setAdding} />
    </div>
  );
}

function OwnerFilter({ owners, value, onChange }: { owners: string[]; value: string; onChange: (owner: string) => void }) {
  if (owners.length < 2) return null;
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Show tasks for">
      {[EVERYONE, ...owners].map((o) => (
        <Button key={o || "everyone"} size="sm" variant={value === o ? "default" : "outline"} className="rounded-full" aria-pressed={value === o} onClick={() => onChange(o)}>{o || "Everyone"}</Button>
      ))}
    </div>
  );
}

function TaskList({ tasks, onOpen }: { tasks: Task[]; onOpen: (id: string) => void }) {
  const change = useChangeTask();
  return (
    <ul className="divide-y overflow-hidden rounded-xl border bg-card" aria-label="Tasks">
      {tasks.map((t) => (
        <li key={t.id} className="flex items-center gap-3 px-4 py-3.5">
          <Checkbox checked={t.status === "done"} disabled={change.isPending} onCheckedChange={(on) => change.mutate({ id: t.id, status: on ? "done" : "open" })} aria-label={t.status === "done" ? `Reopen ${t.title}` : `Mark ${t.title} done`} />
          <button type="button" onClick={() => onOpen(t.id)} className="flex min-w-0 flex-1 items-center gap-3 rounded-md text-left outline-none focus-visible:ring-4 focus-visible:ring-ring/40">
            <span className="min-w-0 flex-1">
              <span className={cn("block truncate text-[15px] font-medium", t.status === "done" && "text-muted-foreground line-through")}>{t.title}</span>
              <span className="mt-0.5 block truncate text-xs text-muted-foreground">{t.owner} · due {date(t.due)}{t.source ? ` · ${t.source.title}` : ""}</span>
            </span>
            <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          </button>
        </li>
      ))}
    </ul>
  );
}

function Empty({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed px-6 py-16 text-center">
      <ListTodo className="size-7 text-muted-foreground" aria-hidden />
      <div>
        <p className="text-[15px] font-medium">No tasks yet</p>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">Add a meeting transcript in Lisena and its action points become tasks here.</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <Button asChild><Link href="/l1/ask">Add a meeting in Lisena</Link></Button>
        <Button variant="outline" onClick={onAdd}>Add a task by hand</Button>
      </div>
    </div>
  );
}

/** One task, opened: change its name, owner or day; see the line it came from. */
function TaskSheet({ task, onClose }: { task: Task | null; onClose: () => void }) {
  return (
    <Sheet open={!!task} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-md">
        {task && <TaskForm key={task.id} task={task} onClose={onClose} />}
      </SheetContent>
    </Sheet>
  );
}

function TaskForm({ task, onClose }: { task: Task; onClose: () => void }) {
  const change = useChangeTask();
  const [title, setTitle] = useState(task.title);
  const [owner, setOwner] = useState(task.owner);
  const [due, setDue] = useState(task.due);
  const edited = title !== task.title || owner !== task.owner || due !== task.due;
  const valid = title.trim() && owner.trim() && due;
  return (
    <>
      <SheetHeader className="border-b p-6">
        <SheetTitle className="text-lg leading-snug">{task.title}</SheetTitle>
        <SheetDescription>{task.status === "done" ? `Done${task.doneAt ? ` ${date(task.doneAt)}` : ""}` : `${task.owner} · due ${date(task.due)}`}</SheetDescription>
      </SheetHeader>
      <form className="space-y-5 p-6" onSubmit={(e) => { e.preventDefault(); if (valid) change.mutate({ id: task.id, title: title.trim(), owner: owner.trim(), due }); }}>
        <Field id="task-title" label="Task"><Input id="task-title" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field id="task-owner" label="Owner"><Input id="task-owner" value={owner} onChange={(e) => setOwner(e.target.value)} /></Field>
        <Field id="task-due" label="Due"><Input id="task-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
        {change.isError && <p role="alert" className="text-sm text-risk">It could not be saved. Check the fields and try again.</p>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={!edited || !valid || change.isPending}>Save changes</Button>
          <Button type="button" variant="outline" disabled={change.isPending} onClick={() => change.mutate({ id: task.id, status: task.status === "done" ? "open" : "done" }, { onSuccess: onClose })}>
            {task.status === "done" ? "Reopen" : "Mark done"}
          </Button>
        </div>
      </form>
      {task.source && (
        <section className="border-t p-6">
          <h3 className="mb-3 text-[15px] font-semibold">Said in the meeting</h3>
          <blockquote className="border-l-2 border-primary pl-3 text-sm text-muted-foreground">“{task.source.line}”</blockquote>
          <Link href={`/l2/library?doc=${task.source.documentId}`} className="mt-3 inline-block text-sm text-primary hover:underline">{task.source.title}</Link>
        </section>
      )}
    </>
  );
}

function AddTask({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const add = useAddTask();
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  const close = () => { setTitle(""); setOwner(""); setDue(""); add.reset(); onOpenChange(false); };
  const ready = useMemo(() => title.trim() && owner.trim(), [title, owner]);
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add a task</DialogTitle>
          <DialogDescription>One thing, one owner. Leave the day empty for a week from today.</DialogDescription>
        </DialogHeader>
        <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (ready) add.mutate({ title: title.trim(), owner: owner.trim(), ...(due ? { due } : {}) }, { onSuccess: close }); }}>
          <Field id="new-title" label="Task"><Input id="new-title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Send the plan to Acme" /></Field>
          <Field id="new-owner" label="Owner"><Input id="new-owner" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Sara" /></Field>
          <Field id="new-due" label="Due (optional)"><Input id="new-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
          {add.isError && <p role="alert" className="text-sm text-risk">It could not be added. Try again.</p>}
          <div className="flex justify-between gap-2">
            <Button type="button" variant="ghost" onClick={close}>Cancel</Button>
            <Button type="submit" disabled={!ready || add.isPending}>Add task</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
