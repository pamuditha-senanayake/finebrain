import type { Metadata } from "next";
import { TraceTimeline } from "@/features/l1/memory/trace-timeline";

export const metadata: Metadata = { title: "Trace" };

export default function Page() {
  return <TraceTimeline />;
}
