"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, PageHeader, QueryView } from "@/components/brain/primitives";
import { useLibrarian } from "@/lib/api/hooks";
import { VaultFacts } from "./vault-facts";
import { VaultQueue } from "./vault-queue";

/** Ground truth: what waits for review, one card at a time, and the facts that are true now. */
export function Vault() {
  const librarian = useLibrarian();
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") === "facts" || params.get("fact") ? "facts" : "queue";
  const waiting = librarian.data?.filter((i) => i.status !== "resolved").length;
  return (
    <div>
      <PageHeader title="Ground truth vault" description="Facts with proof." />
      <Tabs value={tab} onValueChange={(next) => router.replace(next === "facts" ? "/l2/vault?tab=facts" : "/l2/vault")}>
        <TabsList>
          <TabsTrigger value="queue">To review {waiting ? <span className="ml-1 text-muted-foreground">{waiting}</span> : null}</TabsTrigger>
          <TabsTrigger value="facts">Facts</TabsTrigger>
        </TabsList>
        <TabsContent value="queue" className="mt-6">
          <QueryView query={librarian} empty={<EmptyState title="Nothing to review" />}>
            {(items) => <VaultQueue items={items} />}
          </QueryView>
        </TabsContent>
        <TabsContent value="facts" className="mt-6">
          <VaultFacts />
        </TabsContent>
      </Tabs>
    </div>
  );
}
