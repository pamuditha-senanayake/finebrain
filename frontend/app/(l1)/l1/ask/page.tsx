import type { Metadata } from "next";
import { AskVoice } from "@/features/l1/ask-voice";

export const metadata: Metadata = { title: "Lisena" };

export default function Page() {
  return <AskVoice />;
}
