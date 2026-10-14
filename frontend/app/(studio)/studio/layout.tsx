import type { ReactNode } from "react";
import { StudioShell } from "@/features/studio/shell";

export default function Layout({ children }: { children: ReactNode }) {
  return <StudioShell>{children}</StudioShell>;
}
