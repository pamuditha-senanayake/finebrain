import type { Metadata } from "next";
import { ResearchLab } from "@/features/research/lab";

export const metadata: Metadata = { title: "Research Lab" };

export default function Page() {
  return <ResearchLab />;
}
