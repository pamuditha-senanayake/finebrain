import type { Metadata } from "next";
import { EntityProtection } from "@/features/l1/entity";

export const metadata: Metadata = { title: "Entity protection" };

export default function Page() {
  return <EntityProtection />;
}
