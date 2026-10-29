import type { Metadata } from "next";
import { Home } from "@/features/home";

export const metadata: Metadata = { title: "FineBrain" };

export default function Page() {
  return <Home />;
}
