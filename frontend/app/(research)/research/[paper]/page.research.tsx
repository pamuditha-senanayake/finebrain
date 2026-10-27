import type { Metadata } from "next";
import { ResearchPaperPage } from "@/features/research/paper";

export const metadata: Metadata = { title: "Research" };

export default function Page() {
  return <ResearchPaperPage />;
}
