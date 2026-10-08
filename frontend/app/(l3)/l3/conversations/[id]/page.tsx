import type { Metadata } from "next";
import { ConversationDetailPage } from "@/features/l3/conversations";

export const metadata: Metadata = { title: "Conversation" };

export default function Page() {
  return <ConversationDetailPage />;
}
