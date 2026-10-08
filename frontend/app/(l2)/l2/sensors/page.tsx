import type { Metadata } from "next";
import { Sensors } from "@/features/l2/sensors";

export const metadata: Metadata = { title: "Sensors" };

export default function Page() {
  return <Sensors />;
}
