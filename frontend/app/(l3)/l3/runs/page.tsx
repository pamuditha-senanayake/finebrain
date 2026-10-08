import type { Metadata } from "next";
import { RunsExplorer } from "@/features/l3/runs";

export const metadata: Metadata = { title: "Runs" };

export default function Page() {
  return <RunsExplorer />;
}
