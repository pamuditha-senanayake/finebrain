import type { Metadata } from "next";
import { SkillEditor } from "@/features/l2/skills";

export const metadata: Metadata = { title: "Skill" };

export default function Page() {
  return <SkillEditor />;
}
