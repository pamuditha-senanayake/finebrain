// ask-go.ts: "go to the library", "open audit trail": find the page a person asked for among the pages they may open.
// Used by: components/shell/ask-orb.tsx and features/l1/ask-voice.tsx. No match means the words are a normal question.
import type { Human } from "@/contracts";
import { canView } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { NAV, RESEARCH_NAV } from "@/lib/nav";

// "show me" is left out on purpose: "show me the refund policy" is a question, not a trip.
const WANTS_A_PAGE = /^\s*(?:please\s+)?(?:go to|go|open|take me to|navigate to|switch to)\s+(?:the\s+)?(.+?)(?:\s+(?:page|screen|tab))?\s*[.?!]?\s*$/i;
const ALIASES: Record<string, string> = { approvals: "/l1/digest", approval: "/l1/digest", home: "/", overview: "/l1", chat: "/l1/ask" };

export type Destination = { label: string; href: string };

function score(phrase: string, label: string): number {
  if (phrase === label) return 3;
  if (label.startsWith(phrase) || phrase.startsWith(label)) return 2;
  return label.includes(phrase) ? 1 : 0;
}

/** The page asked for, or null when the words do not name one the person may open. */
export function findPage(question: string, user: Human | null): Destination | null {
  const phrase = WANTS_A_PAGE.exec(question)?.[1]?.trim().toLowerCase();
  if (!phrase || !user) return null;

  // Step 1: every page this person may open, with its readable name
  const pages = [...NAV, RESEARCH_NAV].filter((area) => canView(user, area.area)).flatMap((area) => area.items.map((item) => ({ label: t(item.label), href: item.href })));

  // Step 2: an alias wins, else the best matching name
  const aliased = ALIASES[phrase];
  if (aliased) return pages.find((page) => page.href === aliased) ?? null;
  const ranked = pages.map((page) => ({ page, points: score(phrase, page.label.toLowerCase()) })).filter((x) => x.points > 0);
  return ranked.sort((a, b) => b.points - a.points)[0]?.page ?? null;
}
