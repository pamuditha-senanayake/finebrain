import type { Metadata } from "next";
import { WorkflowStudio } from "@/features/studio/studio";

export const metadata: Metadata = { title: "Workflow Studio" };

export default function Page() {
  return <WorkflowStudio />;
}
