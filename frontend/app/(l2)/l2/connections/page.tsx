import type { Metadata } from "next";
import { Suspense } from "react";
import { ConnectionsPage } from "@/features/connect/connections-page";

export const metadata: Metadata = { title: "Connections" };

export default function Page() {
  return (
    <Suspense>
      <ConnectionsPage />
    </Suspense>
  );
}
