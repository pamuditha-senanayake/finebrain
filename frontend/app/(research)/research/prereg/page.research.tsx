import type { Metadata } from "next";
import { Preregistrations } from "@/features/research/prereg";

export const metadata: Metadata = { title: "Preregistrations" };

export default function Page() {
  return <Preregistrations />;
}
