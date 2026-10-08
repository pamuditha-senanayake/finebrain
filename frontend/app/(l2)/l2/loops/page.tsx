import type { Metadata } from "next";
import { LoopsIndex } from "@/features/l2/loops";

export const metadata: Metadata = { title: "Loops" };

export default function Page() {
  return <LoopsIndex />;
}
