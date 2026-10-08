import type { Metadata } from "next";
import { SkillsStudio } from "@/features/l2/skills";

export const metadata: Metadata = { title: "Skills studio" };

export default function Page() {
  return <SkillsStudio />;
}
