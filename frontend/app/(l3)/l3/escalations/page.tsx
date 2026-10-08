import type { Metadata } from "next";
import { Escalations } from "@/features/l3/escalations";

export const metadata: Metadata = { title: "Escalations" };

export default function Page() {
  return <Escalations />;
}
