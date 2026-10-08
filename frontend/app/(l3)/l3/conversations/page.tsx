import type { Metadata } from "next";
import { ConversationsIndex } from "@/features/l3/conversations";

export const metadata: Metadata = { title: "Live conversations" };

export default function Page() {
  return <ConversationsIndex />;
}
