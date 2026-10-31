"use client";

// skills-from-traces.tsx: the "From traces" tab. Skills nobody wrote down, drafted from patterns of real work,
// one draft at a time with how many traces back it. Nothing goes live until an L1 user approves it.
// Used by: skills.tsx. Uses: features/l1/memory/areas.ts, components/brain, lib/api/hooks.
import Link from "next/link";
import type { ExtractedSkill } from "@/contracts";
import { CardPager } from "@/components/brain/card-pager";
import { EmptyState, QueryView, SampleBadge } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { AREA_COLOR } from "@/features/l1/memory/areas";
import { NotConnected, notConnected } from "@/features/l1/memory/memory";
import { SendDraft } from "@/features/l1/memory/memory-actions";
import { useExtractedSkills, useMemoryMap } from "@/lib/api/hooks";
import { pct } from "@/lib/format";

// Config
const STATE_LABEL: Record<ExtractedSkill["state"], string> = { draft: "Draft", in_review: "In review", approved: "Approved", rejected: "Rejected" };

export function useDraftCount() {
  return useExtractedSkills().data?.filter((s) => s.state === "draft" || s.state === "in_review").length ?? 0;
}

export function SkillsFromTraces() {
  const drafts = useExtractedSkills();
  const map = useMemoryMap();
  const names = new Map(map.data?.areas.map((a) => [a.key, a.name]));
  return (
    <div className="space-y-4 pt-2">
      <p className="mx-auto max-w-2xl text-[15px] text-muted-foreground">Ways of working the brain found in past work, not written by anyone.</p>
      {notConnected(drafts.error) ? <NotConnected /> : <QueryView query={drafts} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No skills found yet" description="A pattern needs at least 20 traces that end the same way." />}>
        {(d) => <CardPager items={d} getId={(s) => s.id} label="Skill drafts" testId="skill-drafts" render={(s) => <DraftCard skill={s} areaName={names.get(s.area) ?? s.area} sample={!!map.data?.isSample} />} />}
      </QueryView>}
    </div>
  );
}

function DraftCard({ skill, areaName, sample }: { skill: ExtractedSkill; areaName: string; sample: boolean }) {
  return (
    <div className="space-y-7 rounded-2xl border bg-card p-7">
      <div className="space-y-1.5">
        <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <span className="size-2.5 rounded-full" style={{ background: AREA_COLOR[skill.area] }} aria-hidden />
          {areaName} · {STATE_LABEL[skill.state]} {sample && <SampleBadge />}
        </p>
        <h2 className="text-xl font-semibold">{skill.name}</h2>
      </div>
      <dl className="grid grid-cols-3 gap-4">
        <Figure label="Traces" value={String(skill.support)} hint="back it" />
        <Figure label="Same ending" value={pct(skill.sameOutcomeShare)} hint="of the same steps" />
        <Figure label="Follow rate" value={pct(skill.followRate)} hint="latest week" />
      </dl>
      <ol className="space-y-2" aria-label="Steps">
        {skill.steps.map((step, i) => (
          <li key={step.activity} className="flex gap-3 text-[15px]">
            <span className="w-5 shrink-0 text-right tabular-nums text-muted-foreground">{i + 1}</span>
            {step.title}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-start gap-3">
        <SendDraft skill={skill} sample={sample} />
        <Button asChild variant="outline"><Link href={`/l1/memory/traces?area=${skill.area}`}>See the traces</Link></Button>
      </div>
    </div>
  );
}

function Figure({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div>
      <dt className="text-[12px] font-medium uppercase tracking-[0.07em] text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
      <dd className="text-[13px] text-muted-foreground">{hint}</dd>
    </div>
  );
}
