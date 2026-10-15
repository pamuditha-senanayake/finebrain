"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, ArrowUp, Compass, FileText, Globe2, ListChecks, Lock, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AskAnswer } from "@/contracts";
import { useAsk } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date } from "@/lib/format";
import { guideFor } from "@/lib/page-context";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

type Scope = "page" | "system";
type Msg =
  | { id: number; role: "user"; text: string; scope: Scope | null }
  | { id: number; role: "brain"; answer: AskAnswer }
  | { id: number; role: "note"; text: string }
  // The brain asks what a question is about before answering it, once per page.
  | { id: number; role: "choose"; question: string; picked: Scope | null };

const SYSTEM_SUGGESTIONS = ["What is our refund window?", "When does the finebase.lk domain renew?", "What are support hours?", "What is the VAT registration status?"];

/** A living orb: it breathes when idle and swirls while the brain is reading. */
function Orb({ busy, size = 28 }: { busy?: boolean; size?: number }) {
  return (
    <span className={cn("ask-orb relative inline-block shrink-0 rounded-full", busy && "ask-orb-busy")} style={{ width: size, height: size }} aria-hidden>
      <span className="ask-orb-core absolute inset-0 rounded-full" />
      <span className="ask-orb-shine absolute rounded-full" />
    </span>
  );
}

/** Words arrive one after another, like a reply being written. Older answers appear whole. */
function Streamed({ text, live }: { text: string; live: boolean }) {
  const reduce = useReducedMotion();
  const words = useMemo(() => text.split(" "), [text]);
  const [n, setN] = useState(live && !reduce ? 0 : words.length);
  useEffect(() => {
    if (!live || reduce) return;
    const id = setInterval(() => setN((v) => (v >= words.length ? (clearInterval(id), v) : v + 1)), 22);
    return () => clearInterval(id);
  }, [live, reduce, words.length]);
  return <>{words.slice(0, n).join(" ")}{n < words.length && <span className="ask-caret" aria-hidden />}</>;
}

export function AskPanel() {
  const open = useUi((s) => s.askOpen);
  const setOpen = useUi((s) => s.setAskOpen);
  const pathname = usePathname();
  const guide = useMemo(() => guideFor(pathname), [pathname]);
  const hasPage = guide.key !== "home";
  const { user } = useCurrentUser();
  const reduce = useReducedMotion();
  const ask = useAsk();
  // Null until the conversation settles it: the brain asks "this page or the whole system?" on the first question.
  const [scope, setScope] = useState<Scope | null>(null);
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [focused, setFocused] = useState(false);
  const seq = useRef(0);
  const lastPath = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const effective: Scope | null = hasPage ? scope : "system";

  // Moving to another page leaves a note, so answers always read in the context they were asked in.
  useEffect(() => {
    if (!open) return;
    if (lastPath.current !== null && lastPath.current !== pathname && msgs.length) {
      setMsgs((m) => [...m, { id: ++seq.current, role: "note", text: `Now on ${guide.title}` }]);
      setScope(null);
    }
    lastPath.current = pathname;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, open]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
  }, [msgs.length, ask.isPending, reduce]);
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 120);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const answer = useCallback(
    async (text: string, sc: Scope) => {
      try {
        const a = await ask.mutateAsync({ question: text, page: { path: pathname + (typeof window !== "undefined" ? window.location.search : ""), scope: sc } });
        setMsgs((m) => [...m, { id: ++seq.current, role: "brain", answer: a }]);
      } catch {
        /* the error state below shows ask.error */
      }
    },
    [ask, pathname],
  );

  /** Ask a question. A suggestion knows its scope; a typed question asks for one if the conversation has not settled it. */
  const submit = useCallback(
    (question: string, known?: Scope) => {
      const text = question.trim();
      if (!text || ask.isPending) return;
      setQ("");
      const sc = known ?? effective;
      if (known && hasPage) setScope(known);
      setMsgs((m) => [...m, { id: ++seq.current, role: "user", text, scope: sc }, ...(sc ? [] : [{ id: ++seq.current, role: "choose" as const, question: text, picked: null }])]);
      if (sc) void answer(text, sc);
    },
    [ask.isPending, effective, hasPage, answer],
  );

  const choose = (id: number, question: string, sc: Scope) => {
    setScope(sc);
    setMsgs((m) => m.map((x) => (x.id === id && x.role === "choose" ? { ...x, picked: sc } : x)));
    void answer(question, sc);
  };

  const suggestions: { text: string; scope: Scope }[] = [
    ...(hasPage ? guide.suggestions.slice(0, 3).map((t) => ({ text: t, scope: "page" as const })) : []),
    ...SYSTEM_SUGGESTIONS.slice(0, hasPage ? 2 : 4).map((t) => ({ text: t, scope: "system" as const })),
  ];
  const lastBrain = [...msgs].reverse().find((m) => m.role === "brain")?.id;

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          key="ask"
          role="complementary"
          aria-label="Ask the Brain"
          className="ask-surface fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l shadow-2xl sm:w-[460px]"
          initial={reduce ? { opacity: 0 } : { x: 48, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={reduce ? { opacity: 0 } : { x: 48, opacity: 0 }}
          transition={{ type: "spring", stiffness: 380, damping: 36 }}
        >
          <div className="ask-aurora pointer-events-none absolute inset-x-0 top-0 h-56" aria-hidden />

          <header className="relative flex items-center gap-3 px-5 pb-3 pt-4">
            <Orb busy={ask.isPending} size={34} />
            <div className="min-w-0 flex-1">
              <h2 className="text-[15px] font-bold leading-tight tracking-tight">Ask the Brain</h2>
              <p className="truncate text-[11px] text-muted-foreground">Uses only what {user?.name ?? "you"} may see. Facts show when they are true.</p>
            </div>
            <button type="button" onClick={() => setOpen(false)} className="grid size-8 place-items-center rounded-full text-muted-foreground transition hover:bg-foreground/8 hover:text-foreground" aria-label="Close">
              <X className="size-4" />
            </button>
          </header>

          <div className="relative min-h-0 flex-1 space-y-5 overflow-y-auto px-5 pb-4 pt-1" aria-live="polite">
            {msgs.length === 0 && !ask.isPending && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="pt-4">
                <div className="mb-6 flex flex-col items-center text-center">
                  <Orb size={64} />
                  <p className="mt-5 text-xl font-bold tracking-tight">What do you want to know?</p>
                  <p className="mt-1.5 max-w-[340px] text-sm text-muted-foreground">Ask about this page or anything in the company. Answers cite verified facts.</p>
                </div>
                <div className="flex flex-col gap-2">
                  {suggestions.map((s, i) => (
                    <motion.button key={s.text} type="button" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i + 0.1 }} onClick={() => submit(s.text, s.scope)} className="group flex items-center gap-3 rounded-2xl border bg-card/70 px-4 py-3 text-left text-sm font-medium shadow-xs backdrop-blur transition hover:-translate-y-px hover:border-primary/40 hover:bg-card hover:shadow-sm">
                      {s.scope === "page" ? <FileText className="size-4 shrink-0 text-muted-foreground" aria-label="About this page" /> : <Globe2 className="size-4 shrink-0 text-muted-foreground" aria-label="Whole system" />}
                      <span className="flex-1">{s.text}</span>
                      <ArrowRight className="size-3.5 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
                    </motion.button>
                  ))}
                </div>
              </motion.div>
            )}

            {msgs.map((m) =>
              m.role === "note" ? (
                <div key={m.id} className="flex items-center gap-3 text-[11px] font-medium text-muted-foreground" role="separator">
                  <span className="h-px flex-1 bg-border" /> <Compass className="size-3" /> {m.text} <span className="h-px flex-1 bg-border" />
                </div>
              ) : m.role === "user" ? (
                <motion.div key={m.id} initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} className="flex flex-col items-end gap-1">
                  <div className="max-w-[88%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground shadow-sm">{m.text}</div>
                  {m.scope && <span className="px-1 text-[11px] text-muted-foreground">{m.scope === "page" ? `about ${guide.title}` : "whole system"}</span>}
                </motion.div>
              ) : m.role === "choose" ? (
                <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                  <Orb size={24} />
                  <div className="min-w-0 flex-1 space-y-3">
                    <p className="text-sm leading-relaxed">Is this about {guide.title}, or the whole system?</p>
                    <div className="flex flex-wrap gap-2" role="group" aria-label="What is this about">
                      {([["page", guide.title, FileText], ["system", "Whole system", Globe2]] as const).map(([k, label, Icon]) => (
                        <button key={k} type="button" disabled={m.picked !== null || ask.isPending} onClick={() => choose(m.id, m.question, k)} className={cn("inline-flex h-9 items-center gap-2 rounded-full border px-4 text-sm font-medium transition", m.picked === k ? "border-primary bg-primary text-primary-foreground" : "bg-card/70 hover:border-primary/40 hover:bg-card disabled:opacity-50")}>
                          <Icon className="size-4" /> {label}
                        </button>
                      ))}
                    </div>
                  </div>
                </motion.div>
              ) : (
                <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                  <Orb size={24} />
                  <div className="min-w-0 flex-1 space-y-3">
                    <p className="text-sm leading-relaxed" data-testid="ask-answer">
                      <Streamed text={m.answer.answer} live={m.id === lastBrain} />
                      {m.answer.citations.map((c, i) => (
                        <sup key={c.id} className="ml-0.5 font-mono text-[10px] font-bold text-primary">[{i + 1}]</sup>
                      ))}
                    </p>
                    {m.answer.guide && m.answer.guide.length > 0 && (
                      <div className="rounded-2xl border bg-card/70 p-3.5 backdrop-blur">
                        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-primary"><ListChecks className="size-3.5" /> On this page</div>
                        <ol className="space-y-1.5 text-[13px]">
                          {m.answer.guide.map((g, i) => (
                            <li key={i} className="flex gap-2.5"><span className="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-primary/12 text-[10px] font-bold text-primary">{i + 1}</span><span>{g}</span></li>
                          ))}
                        </ol>
                      </div>
                    )}
                    {m.answer.citations.length > 0 && (
                      <ol className="flex flex-col gap-1.5">
                        {m.answer.citations.map((c, i) => (
                          <li key={c.id}>
                            <Link href={c.href} onClick={() => setOpen(false)} className="group flex items-start gap-2.5 rounded-xl border bg-card/60 px-3 py-2 text-xs transition hover:border-primary/40 hover:bg-card">
                              <span className="mt-px font-mono font-bold text-primary">{i + 1}</span>
                              <span className="min-w-0">
                                <span className="block font-semibold group-hover:underline">{c.label}</span>
                                <span className="text-muted-foreground">{c.kind} · true from {date(c.validFrom)}{c.validTo ? ` to ${date(c.validTo)}` : ", still valid"}</span>
                              </span>
                            </Link>
                          </li>
                        ))}
                      </ol>
                    )}
                    {m.answer.actions && m.answer.actions.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {m.answer.actions.map((a) => (
                          <Link key={a.href} href={a.href} onClick={() => setOpen(false)} className="inline-flex h-7 items-center gap-1 rounded-full border bg-card/70 px-3 text-xs font-semibold transition hover:border-primary/40 hover:text-primary">
                            {a.label} <ArrowRight className="size-3" />
                          </Link>
                        ))}
                      </div>
                    )}
                    {m.answer.withheld > 0 && (
                      <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Lock className="size-3" /> {m.answer.withheld} matching facts are above your access level and were not used.</p>
                    )}
                  </div>
                </motion.div>
              ),
            )}

            {ask.isPending && (
              <div className="flex items-center gap-3" role="status">
                <Orb busy size={24} />
                <span className="ask-shimmer text-sm font-medium">{scope === "page" && hasPage ? `Reading ${guide.title}…` : "Searching what you may see…"}</span>
              </div>
            )}
            {ask.error && <p className="text-sm text-risk">{ask.error.message}</p>}
            <div ref={endRef} />
          </div>

          <form
            className="relative px-4 pb-4 pt-1"
            onSubmit={(e) => {
              e.preventDefault();
              submit(q);
            }}
          >
            <div className={cn("ask-composer rounded-2xl border bg-card/90 p-2 shadow-lg backdrop-blur transition", (focused || ask.isPending) && "beam border-transparent")}>
              <textarea
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), submit(q))}
                placeholder="Ask anything…"
                aria-label="Question"
                rows={1}
                className="block max-h-32 min-h-10 w-full resize-none bg-transparent px-2 py-1.5 text-[15px] outline-none placeholder:text-muted-foreground"
              />
              <div className="flex items-center justify-between gap-2 px-1 pt-1">
                {effective ? (
                  <button type="button" disabled={!hasPage} onClick={() => setScope(effective === "page" ? "system" : "page")} title={hasPage ? "Switch what you are asking about" : undefined} className="inline-flex items-center gap-1.5 rounded-full bg-foreground/6 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:text-foreground disabled:hover:text-muted-foreground">
                    {effective === "page" ? <FileText className="size-3.5" /> : <Globe2 className="size-3.5" />}
                    {effective === "page" ? guide.title : "Whole system"}
                  </button>
                ) : <span />}
                <button type="submit" disabled={!q.trim() || ask.isPending} aria-label="Ask" className="grid size-8 place-items-center rounded-full bg-primary text-primary-foreground shadow-sm transition hover:scale-105 hover:shadow-md disabled:scale-100 disabled:opacity-40 disabled:shadow-none">
                  <ArrowUp className="size-4" />
                </button>
              </div>
            </div>
          </form>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
