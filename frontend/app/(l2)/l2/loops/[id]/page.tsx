import type { Metadata } from "next";
import { LoopDetail } from "@/features/l2/loops";

export const metadata: Metadata = { title: "Loop" };

export default function Page() {
  return <LoopDetail />;
}
