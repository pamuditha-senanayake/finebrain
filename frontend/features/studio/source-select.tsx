"use client";

// source-select.tsx: a sensor's Source, picked from the workspace's real connections that send messages, so a workflow
// only ever listens to something that exists. A seeded channel sensor (email, chat) keeps its channel; a value that is
// neither shows as not a connection. Used by: parts.tsx (ItemForm). Uses: lib/api/connections.ts.
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useConnections } from "@/lib/api/connections";

const CHANNELS = ["email", "chat", "webhook", "poll", "upload", "clarity_export", "calendar"]; // what keyword rules route by
const NONE = "__none";

export function SourceSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const connections = useConnections();
  if (connections.isLoading) return <Input disabled placeholder="Loading connections…" aria-label="Source" />;
  // No list to choose from (a demo workspace, or no right to see connections): type it, and the review checks it
  if (connections.error || !connections.data) return <Input value={value} onChange={(e) => onChange(e.target.value)} aria-label="Source" />;

  const feeds = connections.data.filter((c) => c.feed);
  if (feeds.length === 0 && !value) {
    return (
      <p className="text-sm text-muted-foreground">
        No connection sends messages yet. <Link href="/l2/connections" className="text-primary underline-offset-2 hover:underline">Create one in Connections</Link>
      </p>
    );
  }
  const known = feeds.some((c) => c.id === value);
  const other = value && !known ? (CHANNELS.includes(value) ? `${value} channel (keyword rules)` : `${value} (not a connection)`) : null;
  return (
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
      <SelectTrigger className="w-full" aria-label="Source connection"><SelectValue /></SelectTrigger>
      <SelectContent>
        {!value && <SelectItem value={NONE}>Pick a connection</SelectItem>}
        {other && <SelectItem value={value}>{other}</SelectItem>}
        {feeds.map((c) => (
          <SelectItem key={c.id} value={c.id}>{c.status === "live" ? c.name : `${c.name} · ${c.status}`}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
