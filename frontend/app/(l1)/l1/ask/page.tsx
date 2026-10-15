import type { Metadata } from "next";
import { AskVoice } from "@/features/l1/ask-voice";

export const metadata: Metadata = { title: "Ask the Brain" };

export default function Page() {
  return <AskVoice />;
}
