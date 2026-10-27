import type { Metadata } from "next";
import { ResearchHome } from "@/features/research/home";

export const metadata: Metadata = { title: "Research" };

export default function Page() {
  return <ResearchHome />;
}
