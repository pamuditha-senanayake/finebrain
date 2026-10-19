"use client";

// hq-offline.tsx: shown when the people of a tenant cannot be loaded, which is how a real tenant (Finebase HQ) looks when
// its backend is not reachable. Says so calmly, lets the person retry, or open the demo. Used by: app-shell.tsx.
import { PlugZap } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useUi } from "@/lib/store";

export function HqOffline({ onRetry }: { onRetry: () => void }) {
  const setTenant = useUi((s) => s.setTenant);
  const router = useRouter();

  // Step 1: leave for the demo, which needs no backend
  function openDemo() {
    setTenant("demo-fbl");
    router.push("/");
  }

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-24 text-center" role="status">
      <PlugZap className="size-8 text-muted-foreground" aria-hidden />
      <h2 className="text-xl font-semibold tracking-tight">Not connected</h2>
      <p className="text-[15px] leading-relaxed text-muted-foreground">The brain behind this workspace did not answer.</p>
      <div className="flex gap-2">
        <Button onClick={onRetry}>Retry</Button>
        <Button variant="outline" onClick={openDemo}>Open demo</Button>
      </div>
    </div>
  );
}
