import type { Metadata } from "next";
import { LabRun } from "@/features/research/lab-run";

export const metadata: Metadata = { title: "Lab run" };

export default function Page() {
  return <LabRun />;
}
