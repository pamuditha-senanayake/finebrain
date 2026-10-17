import type { Metadata } from "next";
import { ClaudeMcp } from "@/features/connect/claude-mcp";

export const metadata: Metadata = { title: "Use in Claude" };

export default function Page() {
  return <ClaudeMcp />;
}
