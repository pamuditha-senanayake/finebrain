// ask-go.ts: "go to the library", "can you open the audit trail please": find the page a person asked for among the pages
// they may open. Spoken requests are forgiving: polite words around it are fine, and a near-miss name ("audit trial") still
// matches. Used by: components/shell/ask-orb.tsx (for lib/voice/agent.ts). No match means the words are a normal question.
import type { Human } from "@/contracts";
import { canView } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { NAV, RESEARCH_NAV } from "@/lib/nav";

// Config
// "show me" is left out on purpose: "show me the refund policy" is a question, not a trip.
const LEAD_IN = /^(?:(?:hey|hi|ok|okay|so|lisena|please|can you|could you|would you|will you|i want to|i'd like to|let's|lets)[\s,]+)*/i;
const GO = /^(?:go to|go|open up|open|take me to|bring me to|navigate to|switch to|jump to|show the)\s+(?:the\s+|my\s+|our\s+)?(.+)$/i;
const TAIL = /(?:\s+(?:page|screen|tab|section|please|for me|now|thanks|thank you))+$/i;
const ALIASES: Record<string, string> = { approvals: "/l1/digest", approval: "/l1/digest", review: "/l1/digest", inbox: "/l1/digest", home: "/", overview: "/l1", chat: "/l1/ask", tasks: "/l1/tasks", todo: "/l1/tasks", spending: "/l1/spending", budget: "/l1/spending", expenses: "/l1/spending", studio: "/studio", graph: "/l2/graph", vault: "/l2/vault", runs: "/l3/runs", agents: "/l3" };
const CLOSE_ENOUGH = 0.6; // share of a page name's words that must match

export type Destination = { label: string; href: string };

/** Every page this person may open, with its readable name. */
export function pagesFor(user: Human | null): Destination[] {
  if (!user) return [];
  return [...NAV, RESEARCH_NAV].filter((area) => canView(user, area.area)).flatMap((area) => area.items.map((item) => ({ label: t(item.label), href: item.href })));
}

/** The page asked for, or null when the words do not name one the person may open. */
export function findPage(question: string, user: Human | null): Destination | null {
  const phrase = pagePhrase(question);
  if (!phrase || !user) return null;
  const pages = pagesFor(user);
  // Step 1: an alias wins
  const aliased = ALIASES[phrase] ?? ALIASES[phrase.replace(/s$/, "")];
  if (aliased) return pages.find((page) => page.href === aliased) ?? null;
  // Step 2: else the closest page name, if close enough
  const ranked = pages.map((page) => ({ page, points: closeness(phrase, page.label.toLowerCase()) })).filter((x) => x.points >= CLOSE_ENOUGH);
  return ranked.sort((a, b) => b.points - a.points)[0]?.page ?? null;
}

/** "Could you open the audit trail page, please?" → "audit trail". */
function pagePhrase(question: string): string | null {
  const plain = question.trim().replace(/[.?!,]+$/g, "").replace(LEAD_IN, "");
  const named = GO.exec(plain)?.[1];
  return named ? named.replace(TAIL, "").trim().toLowerCase() : null;
}

/** How much of the page name the phrase covers, word by word, allowing a small slip per word. A full match scores a bit more. */
function closeness(phrase: string, label: string): number {
  if (phrase === label) return 2;
  const said = phrase.split(/\s+/);
  const named = label.split(/\s+/).filter((word) => word !== "and");
  const hits = named.filter((word) => said.some((heard) => sameWord(heard, word))).length;
  const extra = Math.max(0, said.length - named.length) * 0.1; // "audit trail of refunds" is a little further than "audit trail"
  return hits / named.length - extra;
}

function sameWord(a: string, b: string): boolean {
  if (a === b) return true;
  const slips = b.length >= 7 ? 2 : b.length >= 4 ? 1 : 0;
  return slips > 0 && Math.abs(a.length - b.length) <= slips && editDistance(a, b) <= slips;
}

/** Letters added, dropped, changed or swapped ("trial" for "trail" is one slip). */
function editDistance(a: string, b: string): number {
  const d = Array.from({ length: a.length + 1 }, (_, i) => Array.from({ length: b.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}
