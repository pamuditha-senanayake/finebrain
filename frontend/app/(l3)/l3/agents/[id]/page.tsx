import type { Metadata } from "next";
import { AgentProfile } from "@/features/l3/agent-profile";

export const metadata: Metadata = { title: "Agent profile" };

export default function Page() {
  return <AgentProfile />;
}
