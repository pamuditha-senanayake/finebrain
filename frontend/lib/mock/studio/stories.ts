// Why each workflow exists: the problem, how it is handled today, and BDD scenarios for the cases it handles.
// `cover` names the parts that handle a case; the seed turns names into ids. `draftStory` writes a first story
// for a problem someone describes in chat, so the person can confirm the cases before anything is built.
import type { Scenario, Story } from "@/contracts";

type Case = Omit<Scenario, "id" | "coveredBy"> & { cover: string[] };
type StoryDef = { problem: string; today: string; cases: Case[] };

export const STORIES: Record<string, StoryDef> = {
  care: {
    problem: "Customers wait hours for answers the team already knows, and goodwill credits are given inconsistently.",
    today: "Two people read the inbox and chat by hand, search old threads for answers, and decide credits case by case.",
    cases: [
      { title: "Product question on chat", given: ["a customer asks how to export invoices on chat"], when: "nobody on the team is online", then: ["the customer waits until the next morning", "the answer is retyped from an old thread"], goal: "An answer with a cited help article in under a minute.", cover: ["Answer product question"] },
      { title: "Outage hurt a customer's usage", given: ["a customer lost two hours of usage in an outage", "they ask for compensation"], when: "the request reaches the inbox", then: ["the credit depends on who replies", "some customers get nothing, others get too much"], goal: "A goodwill credit inside the cap, the same for everyone, logged in the care report.", cover: ["Goodwill credit", "Goodwill credit cap"] },
      { title: "Customer shares personal data", given: ["a customer pastes a card number into chat"], when: "the message is stored", then: ["the number sits unmasked in the thread"], goal: "Personal data is masked by default and every reveal is audited.", cover: ["Personal data masking"] },
    ],
  },
  refunds: {
    problem: "Refund requests take days, and nobody can say for sure whether a refund was inside policy.",
    today: "Support forwards each request to finance, who checks the purchase date in the payment gateway and refunds by hand.",
    cases: [
      { title: "Refund inside the window", given: ["a customer bought a plan 12 days ago", "the amount is LKR 8,000"], when: "they ask for a refund", then: ["the request waits 2 to 3 days for finance", "the customer chases twice"], goal: "Refunded automatically within minutes, with the policy cited in the register.", cover: ["Refund inside policy", "Refund window"] },
      { title: "Refund above the threshold", given: ["a customer asks for LKR 80,000 back"], when: "the request arrives", then: ["finance refunds it without a second check"], goal: "Escalated to a person with the facts attached, never refunded automatically.", cover: ["Refund auto threshold"] },
      { title: "Request after the window closed", given: ["the purchase was 45 days ago"], when: "the customer asks for a refund", then: ["the answer depends on who reads it"], goal: "A polite, consistent decline that cites the refund window.", cover: ["Refund window"] },
    ],
  },
  billing: {
    problem: "Failed payments and overdue invoices slip through, and receipts pile up in the finance inbox.",
    today: "Finance checks the gateway and bank feed once a week and types expenses into a sheet at month end.",
    cases: [
      { title: "Card payment fails", given: ["a customer's monthly charge fails"], when: "the gateway reports the failure", then: ["nobody notices for a week", "the customer churns silently"], goal: "A retry and a friendly reminder the same day, tracked in revenue health.", cover: ["Failed payment recovery"] },
      { title: "Invoice overdue by 7 days", given: ["a service invoice is 7 days overdue"], when: "the daily check runs", then: ["the chase depends on someone remembering"], goal: "A chase on a fixed schedule, and any write off needs the Finance Director.", cover: ["Receivables chasing", "Write offs"] },
      { title: "Receipt arrives by email", given: ["a supplier emails a receipt"], when: "it lands in the finance inbox", then: ["it is typed in by hand weeks later"], goal: "Captured into the expense log the day it arrives.", cover: ["Expense capture"] },
    ],
  },
  sales: {
    problem: "Good leads go cold because follow ups and quotes take too long.",
    today: "The founder reads every form and chat, and writes quotes from an old spreadsheet.",
    cases: [
      { title: "Lead with buying intent", given: ["a company fills the contact form asking about pricing"], when: "the form is submitted on a Friday evening", then: ["the reply goes out on Monday"], goal: "Qualified and answered within the hour.", cover: ["Lead qualification"] },
      { title: "Qualified lead asks for a quote", given: ["a qualified lead asks for a project quote"], when: "they reply to the follow up", then: ["the quote takes 3 days and the rates differ each time"], goal: "A draft quote against the rate card the same day.", cover: ["Quote for service project"] },
    ],
  },
  meetings: {
    problem: "Booking calls takes several emails, and action items are lost after meetings.",
    today: "People agree times over email and someone may or may not write notes.",
    cases: [
      { title: "Prospect wants a demo", given: ["a prospect asks for a demo next week"], when: "the request arrives", then: ["four emails go back and forth to agree a time"], goal: "A slot booked from the shared calendars in one reply.", cover: ["Meeting arrangement"] },
      { title: "Sprint review ends", given: ["a sprint review was recorded"], when: "the transcript is ready", then: ["action items live in someone's head"], goal: "Action items logged with owners and due dates.", cover: ["Notes to action items"] },
    ],
  },
  onboarding: {
    problem: "New clients wait for access and a clear checklist after signing.",
    today: "The account manager copies last client's checklist and asks IT for access by chat.",
    cases: [
      { title: "Contract signed", given: ["a client signs a retainer contract"], when: "the contract lands in the vault", then: ["onboarding starts a week later"], goal: "A checklist and the access requests the project needs, on the same day.", cover: ["Client onboarding", "Access review"] },
    ],
  },
  delivery: {
    problem: "Client status reports are late and miss SLA breaches.",
    today: "Project leads assemble the report on Friday afternoon from three tools.",
    cases: [
      { title: "Friday report", given: ["a retainer client expects a weekly report"], when: "it is Friday afternoon", then: ["the report is pieced together by hand", "an uptime dip is missed"], goal: "A report from the tracker, repository and uptime monitor, sent on time.", cover: ["Client status report"] },
    ],
  },
  web: {
    problem: "Website updates lag behind releases, and risky pages can change without sign off.",
    today: "Marketing edits the CMS directly whenever someone remembers.",
    cases: [
      { title: "New release ships", given: ["a product release is published"], when: "the release note is ready", then: ["the website mentions it two weeks later"], goal: "Release notes and pages updated the same day.", cover: ["Website content update"] },
      { title: "Someone edits pricing", given: ["a change touches the pricing page"], when: "it is saved", then: ["it goes live with no approval"], goal: "Pricing and legal changes wait for an L1 approval.", cover: ["Pricing and legal pages"] },
    ],
  },
  ux: {
    problem: "We see drop offs in analytics but never turn them into fixes.",
    today: "Someone looks at Clarity once a month and files a ticket that rarely ships.",
    cases: [
      { title: "Checkout friction spikes", given: ["rage clicks on checkout double this week"], when: "the friction signal passes the threshold", then: ["nobody notices until revenue dips"], goal: "An A/B experiment proposed on a sandbox branch.", cover: ["UX experiment proposal"] },
    ],
  },
  reputation: {
    problem: "Public reviews go unanswered or get replies in the wrong tone.",
    today: "Whoever sees a review replies, sometimes days later.",
    cases: [
      { title: "Negative review posted", given: ["a customer posts a 2 star review"], when: "the review site reports it", then: ["it sits unanswered for a week"], goal: "A warm, specific reply after the tone gate, the same day.", cover: ["Public review reply", "Public reply tone"] },
    ],
  },
  incident: {
    problem: "Customers hear about outages from social media before they hear from us.",
    today: "An engineer posts on the status page after the fix, if they remember.",
    cases: [
      { title: "Outage lasts five minutes", given: ["the uptime monitor reports the API down"], when: "the alert lasts five minutes", then: ["the status page stays green", "support gets flooded"], goal: "A clear statement drafted and posted within minutes.", cover: ["Outage communication"] },
    ],
  },
  compliance: {
    problem: "Tax and statutory deadlines turn into last minute scrambles for evidence.",
    today: "Finance collects documents in the week before each deadline.",
    cases: [
      { title: "VAT return due", given: ["a VAT return is due in 14 days", "input invoices for the period are missing"], when: "the hourly readiness scan runs", then: ["the gap is found two days before the deadline"], goal: "The gap is requested from its owner weeks ahead. People still file.", cover: ["Obligation readiness", "VAT evidence pack (sample)"] },
      { title: "Certificate renewal", given: ["a certificate expires in 45 days"], when: "the renewal is tracked", then: ["it is noticed after it expires"], goal: "A renewal reminder with owner and date.", cover: ["Renewal tracking"] },
    ],
  },
  quality: {
    problem: "Agent failures repeat because nobody reviews them systematically.",
    today: "Failures are looked at only when a customer complains.",
    cases: [
      { title: "Failures overnight", given: ["three runs failed yesterday"], when: "it is 02:00", then: ["the same failure happens again the next day"], goal: "Failures classified and fixes drafted on sandbox branches by morning.", cover: ["Overnight failure review"] },
    ],
  },
  knowledge: {
    problem: "Agents answer from stale or conflicting facts.",
    today: "Facts are updated when someone happens to notice they are wrong.",
    cases: [
      { title: "Two facts disagree", given: ["the price list says LKR 4,900 and the help page says LKR 5,500"], when: "the nightly scan runs", then: ["agents quote either price"], goal: "The conflict is found and a resolution proposed to the steward.", cover: ["Freshness and conflicts"] },
    ],
  },
  access: {
    problem: "Agents keep permissions they no longer need, and denied calls are ignored.",
    today: "Access is reviewed once a year in a spreadsheet.",
    cases: [
      { title: "Denied tool call", given: ["an agent is denied a tool it needs"], when: "the denial is logged", then: ["work silently stops"], goal: "A grant proposed for review the same week.", cover: ["Access review"] },
    ],
  },
};

/** Builds the seeded story for a workflow, turning part names into ids. */
export function seededStory(key: string, items: { id: string; name: string }[]): Story | null {
  const def = STORIES[key];
  if (!def) return null;
  return {
    problem: def.problem,
    today: def.today,
    scenarios: def.cases.map(({ cover, ...c }, i) => ({ ...c, id: `${key}-s${i + 1}`, coveredBy: cover.map((n) => items.find((x) => x.name === n)?.id).filter((x): x is string => !!x) })),
  };
}

// ---------------------------------------------------------------- drafting from a described problem

type Domain = { match: RegExp; name: string; today: string; cases: Omit<Case, "cover">[] };

const DOMAINS: Domain[] = [
  {
    match: /\brefund|cancel/, name: "Refund requests", today: "Requests are forwarded to finance and refunded by hand.",
    cases: [
      { title: "Refund inside policy", given: ["a customer bought recently", "the amount is small"], when: "they ask for a refund", then: ["the request waits days for someone to check it"], goal: "Refunded automatically inside policy, with the rule cited." },
      { title: "Refund above the limit", given: ["the amount is above what anyone should approve alone"], when: "the request arrives", then: ["it is refunded without a second check"], goal: "Escalated to a person with the facts attached." },
      { title: "Request outside the window", given: ["the purchase is older than the refund window"], when: "the customer asks", then: ["the answer depends on who reads it"], goal: "A consistent decline that cites the policy." },
    ],
  },
  {
    match: /\binvoice|payment|overdue|billing|receivable|dunning/, name: "Payments follow up", today: "Someone checks payments when they have time and chases by email.",
    cases: [
      { title: "Payment fails", given: ["a customer's charge fails"], when: "the payment provider reports it", then: ["nobody notices for days"], goal: "A retry and a reminder the same day." },
      { title: "Invoice overdue", given: ["an invoice is past its due date"], when: "the daily check runs", then: ["chasing depends on someone remembering"], goal: "A chase on a fixed schedule, escalated after the third reminder." },
    ],
  },
  {
    match: /\blead|prospect|quote|sales|deal/, name: "Lead follow up", today: "Leads are read by hand and followed up when there is time.",
    cases: [
      { title: "New lead with buying intent", given: ["a lead asks about pricing"], when: "the form is submitted", then: ["the reply goes out days later"], goal: "Qualified and answered within the hour." },
      { title: "Lead asks for a quote", given: ["a qualified lead wants a quote"], when: "they reply", then: ["the quote takes days and rates differ"], goal: "A draft quote against the rate card the same day." },
    ],
  },
  {
    match: /\bsupport|ticket|customer (question|message|email)|inbox|chat|complain/, name: "Customer questions", today: "The team reads every message by hand and searches old threads for answers.",
    cases: [
      { title: "Common question", given: ["a customer asks something answered before"], when: "the message arrives", then: ["they wait hours for a retyped answer"], goal: "An answer with a cited source in under a minute." },
      { title: "Unhappy customer", given: ["a customer is upset about an issue"], when: "they write in", then: ["the reply tone depends on who answers"], goal: "A warm reply, and a person is pulled in when needed." },
    ],
  },
  {
    match: /\bmeeting|calendar|book(ing)?|schedul|action item/, name: "Meetings and follow ups", today: "Times are agreed over email and notes are kept, sometimes.",
    cases: [
      { title: "Someone asks for a call", given: ["a client asks to meet next week"], when: "the request arrives", then: ["several emails go back and forth"], goal: "A slot booked in one reply." },
      { title: "Meeting ends", given: ["a meeting was recorded"], when: "the transcript is ready", then: ["action items are forgotten"], goal: "Action items logged with owners and dates." },
    ],
  },
  {
    match: /\bexpense|receipt|reimburs/, name: "Expense capture", today: "Receipts are typed into a sheet at month end.",
    cases: [
      { title: "Receipt arrives", given: ["a receipt is emailed in"], when: "it lands in the inbox", then: ["it is typed in weeks later, sometimes twice"], goal: "Captured into the expense log the same day." },
    ],
  },
  {
    match: /\bhir(e|ing)|candidate|cv|resume|applicant|recruit/, name: "Hiring pipeline", today: "Applications are read by hand and replies are slow.",
    cases: [
      { title: "New application", given: ["a candidate applies for an open role"], when: "the application arrives", then: ["it waits a week to be read"], goal: "Screened against the role and answered within two days." },
      { title: "Interview booked", given: ["a candidate passes screening"], when: "an interview is needed", then: ["scheduling takes several emails"], goal: "An interview booked from the panel's calendars." },
    ],
  },
  {
    match: /\breport|status|weekly update|dashboard/, name: "Status reporting", today: "Reports are assembled by hand from several tools.",
    cases: [
      { title: "Report due", given: ["a weekly report is expected"], when: "it is Friday", then: ["it is pieced together by hand and arrives late"], goal: "A report built from the source tools, sent on time." },
    ],
  },
];

const GENERIC: Domain = {
  match: /./, name: "New workflow", today: "People handle it by hand, when they have time.",
  cases: [
    { title: "The usual case", given: ["the situation you described happens"], when: "someone needs to act on it", then: ["it is done by hand and takes too long"], goal: "Handled the same day, the same way every time." },
    { title: "The unusual case", given: ["something about it is outside the normal rules"], when: "it comes in", then: ["it waits until someone senior notices"], goal: "Escalated to the right person with the facts attached." },
  ],
};

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** The case the person described, in their own words: the part after "when" is the situation, the rest is the pain. */
function caseFrom(text: string, id: string): Scenario {
  const t = text.trim().replace(/^(we have a problem|our problem is|the problem is|problem)[:,]?\s*/i, "").replace(/[.?!]+$/, "");
  const m = t.match(/^(.*?)\s+(?:when|whenever|if|because|after|every time)\s+(.+)$/i);
  const pain = (m ? m[1] : t).trim();
  // "Candidates wait ... when they apply" reads better as "candidates apply".
  const subject = pain.split(/\s+/)[0] ?? "";
  const cond = m?.[2]?.trim().replace(/^(they|it|he|she)\b/i, subject.toLowerCase());
  const title = cap((cond ?? pain).split(/\s+/).slice(0, 7).join(" "));
  return { id, title, given: ["it is handled by hand today"], when: cond ?? "it comes up", then: [pain.toLowerCase()], goal: "Handled the same day, the same way every time, with a person pulled in when it needs judgment.", coveredBy: [] };
}

/** A first story for a described problem: the person's own case first, then the usual cases for that kind of work. */
export function draftStory(problemText: string, seq: number, skipTitles: string[] = []): { name: string; story: Story } {
  const text = problemText.toLowerCase();
  const domain = DOMAINS.find((d) => d.match.test(text)) ?? GENERIC;
  const problem = cap(problemText.trim().replace(/^(we have a problem|our problem is|the problem is|problem)[:,]?\s*/i, "").replace(/[.?!]*$/, "."));
  const skip = new Set(skipTitles.map((x) => x.toLowerCase()));
  const own = caseFrom(problemText, `draft-${seq}-s1`);
  const rest = domain.cases.filter((c) => !skip.has(c.title.toLowerCase()) && c.title.toLowerCase() !== own.title.toLowerCase()).map((c, i) => ({ ...c, id: `draft-${seq}-s${i + 2}`, coveredBy: [] }));
  return { name: domain.name, story: { problem, today: domain.today, scenarios: [own, ...rest].slice(0, 3) } };
}

/** One more case, written from what the person said. */
export function extraScenario(text: string, seq: number): Scenario {
  const what = text.replace(/^(please\s+)?(add|another)\s+(another\s+|a\s+|one more\s+)?(case|scenario|example)\s*[:,-]?\s*/i, "").trim() || "another situation";
  return { id: `draft-${seq}-x`, title: cap(what).slice(0, 60), given: [what.toLowerCase()], when: "it comes in", then: ["it is handled by hand today"], goal: "Handled the same way every time, or escalated with the facts attached.", coveredBy: [] };
}
