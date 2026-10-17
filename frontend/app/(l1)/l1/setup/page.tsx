import type { Metadata } from "next";
import { SetupPage } from "@/features/setup/interview";

export const metadata: Metadata = { title: "Setup" };

export default function Page() {
  return <SetupPage />;
}
