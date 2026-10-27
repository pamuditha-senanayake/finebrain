import type { Metadata } from "next";
import { NewExperiment } from "@/features/research/lab-new";

export const metadata: Metadata = { title: "New experiment" };

export default function Page() {
  return <NewExperiment />;
}
