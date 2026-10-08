import type { Metadata } from "next";
import { GraphExplorer } from "@/features/l2/graph-explorer";

export const metadata: Metadata = { title: "Knowledge graph" };

export default function Page() {
  return <GraphExplorer />;
}
