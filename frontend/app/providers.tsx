"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useEffect, useState, type ReactNode } from "react";
import { mocksReady } from "@/lib/api/mocks-ready";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { live } from "@/lib/live";
import { useUi } from "@/lib/store";

function MockStarter() {
  useEffect(() => {
    void mocksReady();
  }, []);
  return null;
}

/** Live events invalidate the queries they touch, so lists update without a refresh. */
function LiveBridge() {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  useEffect(() => {
    return live.subscribe(tenantId, (e) => {
      if (e.resources.includes("*")) qc.invalidateQueries({ queryKey: ["t", tenantId] });
      else for (const r of e.resources) qc.invalidateQueries({ queryKey: ["t", tenantId, r] });
    });
  }, [qc, tenantId]);
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: (count, err) => count < 1 && !(err && typeof err === "object" && "status" in err && (err as { status: number }).status < 500) },
        },
      }),
  );
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <TooltipProvider delayDuration={250}>
          <MockStarter />
          <LiveBridge />
          {children}
          <Toaster position="top-right" offset={56} />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
