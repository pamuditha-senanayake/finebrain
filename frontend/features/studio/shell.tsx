"use client";

import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { useCurrentUser } from "@/lib/auth";

/** Workflow Studio sits beside every tier, so the sidebar follows the person's own tier. L3 sees it read only. */
export function StudioShell({ children }: { children: ReactNode }) {
  const { user } = useCurrentUser();
  return <AppShell area={user?.tier ?? "L2"}>{children}</AppShell>;
}
