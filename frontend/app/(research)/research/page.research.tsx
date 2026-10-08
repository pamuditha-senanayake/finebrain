import type { Metadata } from "next";
import { ResearchConsole } from "@/features/research/console";

export const metadata: Metadata = { title: "Research Console" };

export default function Page() {
  return <ResearchConsole />;
}
