"use client";

// connections-page.tsx: picks what the Connections page shows from its address: the list (no query), one connection
// (?c=id), or a new one (?new=type&platform=...). Demo workspaces keep their sample sensors. Used by: app/(l2)/l2/connections.
import { useSearchParams } from "next/navigation";
import { Sensors } from "@/features/l2/sensors";
import type { Kind } from "@/lib/api/connections";
import { useTenantId } from "@/lib/api/hooks";
import { realTenants } from "@/lib/flags";
import { ConnectionDesk } from "./desk";
import { ConnectionsHub } from "./hub";

const KINDS: Kind[] = ["api", "database", "other"];

export function ConnectionsPage() {
  const params = useSearchParams();
  const tenantId = useTenantId();
  if (!realTenants.has(tenantId)) return <Sensors />;
  const connectionId = params.get("c");
  const kind = params.get("new") as Kind | null;
  if (connectionId) return <ConnectionDesk key={connectionId} connectionId={connectionId} />;
  if (kind && KINDS.includes(kind)) {
    const start = { kind, platform: params.get("platform") ?? "", prompt: params.get("prompt") ?? "", from: params.get("from") ?? "" };
    return <ConnectionDesk key={`new:${kind}:${start.platform}:${start.prompt}`} connectionId={null} start={start} />;
  }
  return <ConnectionsHub />;
}
