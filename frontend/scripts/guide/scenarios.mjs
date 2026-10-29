// User guide as BDD scenarios. One source for the written guide (Docs/) and the guide video recording.
// Each step: kw, text, and optionally go (url), as (persona), target (page => Locator), act (page => Promise),
// shot: "before" (show where to act) or "after" (show the result). Default: before when there is an act, else after.

export const PERSONAS = {
  "h-founder": { name: "Nadeesha Perera", title: "Founder", tier: "L1", color: "#4338ca" },
  "h-fd": { name: "Ruwan Jayasinghe", title: "Finance Director", tier: "L1", color: "#0369a1" },
  "h-hcs": { name: "Ishara Fernando", title: "Head of Customer Success", tier: "L1", color: "#be123c" },
  "h-ks": { name: "Dilini Wickramasinghe", title: "Knowledge Steward", tier: "L2", color: "#047857" },
  "h-aiops": { name: "Kasun Bandara", title: "AI Operations Lead", tier: "L2", color: "#b45309" },
  "h-sec": { name: "Tharindu Silva", title: "Security Officer", tier: "L2", color: "#6d28d9" },
  "h-op": { name: "Amaya Gunawardena", title: "Customer Care Operator", tier: "L3", color: "#0f766e" },
  "h-research": { name: "Research Analyst", title: "Research program", tier: "L2", color: "#475569" },
};

export const CHAPTERS = [
  { id: "start", label: "Getting started", color: "#818cf8" },
  { id: "L3", label: "L3 Operations floor", color: "#2dd4bf" },
  { id: "L2", label: "L2 Governance", color: "#4ade80" },
  { id: "L1", label: "L1 Command", color: "#fb7185" },
  { id: "research", label: "Research Console", color: "#94a3b8" },
];

const role = (name) => (p) => p.getByRole("button", { name });
const tableNamed = (name) => (p) => p.getByRole("table", { name });
const h1 = (p) => p.locator("main h1").first();

export const SCENARIOS = [
  // ------------------------------------------------------------ Getting started
  {
    id: "start-persona", chapter: "start", feature: "Getting started", title: "Pick who you are and open your home",
    persona: "h-founder", why: "Each person sees the tier that matches their job. Higher tiers can look down, never up.",
    steps: [
      { kw: "Given", text: "I open FineBrain", go: "/", target: (p) => p.locator("main h1") },
      { kw: "When", text: "I open the persona menu in the top right", target: (p) => p.getByTestId("role-switcher"), act: (p) => p.getByTestId("role-switcher").click() },
      { kw: "And", text: "I choose Ishara Fernando, Head of Customer Success", target: (p) => p.getByTestId("persona-h-hcs"), act: (p) => p.getByTestId("persona-h-hcs").click() },
      { kw: "Then", text: "I land on L1 Command, the leadership home", target: h1 },
      { kw: "And", text: "the red band always tells me I am looking at Production", target: (p) => p.getByTestId("env-banner") },
    ],
  },
  {
    id: "start-palette", chapter: "start", feature: "Getting started", title: "Jump anywhere with the command palette",
    persona: "h-hcs", why: "Press ⌘K from any screen to find agents, skills, policies, approvals or runs.",
    steps: [
      { kw: "Given", text: "I am on any screen", go: "/l1", target: (p) => p.getByRole("button", { name: "Open command palette" }) },
      { kw: "When", text: "I open the palette with ⌘K", target: (p) => p.getByRole("button", { name: "Open command palette" }), act: (p) => p.getByRole("button", { name: "Open command palette" }).click() },
      { kw: "And", text: "I type “Refund Agent”", target: (p) => p.getByRole("dialog"), act: (p) => p.getByPlaceholder(/Search or jump/).fill("Refund Agent"), shot: "after" },
      { kw: "Then", text: "I open the agent straight from the results", target: (p) => p.getByRole("option", { name: /Agent\s*Refund Agent/ }), act: (p) => p.getByRole("option", { name: /Agent\s*Refund Agent/ }).click() },
      { kw: "And", text: "I see its job description: sensors, skills, policies, capabilities", target: h1 },
    ],
  },
  {
    id: "start-ask", chapter: "start", feature: "Getting started", title: "Lisena a question",
    persona: "h-hcs", why: "Answers come only from facts you may see, each with its source and when it is true.",
    steps: [
      { kw: "When", text: "I click Lisena", go: "/l1", target: role("Lisena"), act: (p) => p.getByRole("button", { name: "Lisena" }).click() },
      { kw: "And", text: "I ask “What is our refund window?”", target: role("What is our refund window?"), act: (p) => p.getByRole("button", { name: "What is our refund window?" }).click() },
      { kw: "Then", text: "I get a plain answer with numbered citations", target: (p) => p.getByTestId("ask-answer") },
      { kw: "And", text: "each citation shows when the fact is true in the world", target: (p) => p.getByText(/true from/).first(), after: (p) => p.keyboard.press("Escape") },
    ],
  },

  // ------------------------------------------------------------ L3
  {
    id: "l3-fleet", chapter: "L3", feature: "Operations floor", title: "Watch the agent fleet",
    persona: "h-op", why: "Agents do the work through APIs. This is where people watch them live and step in.",
    steps: [
      { kw: "Given", text: "I am Amaya, a customer care operator", as: "h-op", go: "/l3", target: h1 },
      { kw: "Then", text: "I see every agent with live status, queue, errors and cost", target: tableNamed("Agents") },
      { kw: "When", text: "I switch to the grid view", target: (p) => p.getByRole("radio", { name: "Grid" }), act: (p) => p.getByRole("radio", { name: "Grid" }).click() },
      { kw: "Then", text: "a moving orb means an agent is working right now", target: (p) => p.getByRole("list", { name: "Agents" }).locator("li").first() },
    ],
  },
  {
    id: "l3-run", chapter: "L3", feature: "Operations floor", title: "Inspect any run step by step",
    persona: "h-op", why: "Every decision is traceable: what the agent read, what it decided, which checks it passed.",
    steps: [
      { kw: "Given", text: "I open Runs", go: "/l3/runs", target: tableNamed("Runs") },
      { kw: "When", text: "I filter for customer CUS-1042", target: (p) => p.getByLabel("Filter Runs"), act: (p) => p.getByLabel("Filter Runs").fill("CUS-1042"), shot: "after" },
      { kw: "And", text: "I open the refund run", target: (p) => p.getByRole("row", { name: /CUS-1042/ }).first(), act: (p) => p.getByRole("row", { name: /CUS-1042/ }).first().getByRole("cell").nth(1).click() },
      { kw: "Then", text: "each step is labelled model judgment or deterministic call", target: (p) => p.getByRole("list", { name: "Trace steps" }) },
      { kw: "And", text: "the escalation says exactly why the agent stopped", target: (p) => p.getByRole("heading", { name: "Escalation" }).locator("xpath=ancestor::section") },
    ],
  },
  {
    id: "l3-skillify", chapter: "L3", feature: "Operations floor", title: "Handle an escalation, then Skillify it",
    persona: "h-op", why: "Never do one off work: the way a person solved a case becomes a reusable skill.",
    steps: [
      { kw: "Given", text: "the escalations queue, sorted by risk and waiting time", go: "/l3/escalations", target: tableNamed("Escalations") },
      { kw: "When", text: "I open the refund request from CUS-1042", target: (p) => p.getByRole("row", { name: /CUS-1042/ }), act: (p) => p.getByRole("row", { name: /CUS-1042/ }).click() },
      { kw: "Then", text: "I see the transcript, the agent's reasoning and its proposed actions", target: (p) => p.getByRole("list", { name: "Transcript" }) },
      { kw: "When", text: "I take over the conversation", target: (p) => p.getByTestId("takeover"), act: (p) => p.getByTestId("takeover").click() },
      { kw: "And", text: "I reply to the customer myself", target: (p) => p.getByRole("textbox", { name: "Reply" }), act: async (p) => { await p.getByRole("textbox", { name: "Reply" }).fill("I've asked our head of customer success to review a full refund for you today."); await p.getByRole("button", { name: "Send reply" }).click(); }, shot: "after" },
      { kw: "And", text: "I press Skillify", target: (p) => p.getByTestId("skillify"), act: (p) => p.getByTestId("skillify").click() },
      { kw: "Then", text: "my handling becomes a draft skill on a sandbox branch for L2 to test", target: (p) => p.getByText(/Skillified by/) },
    ],
  },
  {
    id: "l3-templates", chapter: "L3", feature: "Operations floor", title: "Check the template board",
    persona: "h-op", why: "Templates are what each agent must bring back. Stale or partial ones stand out.",
    steps: [
      { kw: "Given", text: "I open the template board", go: "/l3/templates", target: (p) => p.getByRole("radio", { name: /stale/ }).locator("xpath=..") },
      { kw: "When", text: "I filter to stale templates", target: (p) => p.getByRole("radio", { name: /stale/ }), act: (p) => p.getByRole("radio", { name: /stale/ }).click() },
      { kw: "Then", text: "I see which fields are old, who filled them and from which source", target: (p) => p.locator("main ul > li").first() },
    ],
  },

  // ------------------------------------------------------------ L2
  {
    id: "l2-test-skill", chapter: "L2", feature: "Governance", title: "Test a draft skill before it goes live",
    persona: "h-aiops", why: "Nothing goes live blind: sandbox tests and a replay of real runs come before any approval.",
    steps: [
      { kw: "Given", text: "I am Kasun, AI operations lead, on Versioning", as: "h-aiops", go: "/l2/versioning", target: tableNamed("Change requests") },
      { kw: "When", text: "I open “New skill: Late refund with DRI approval”", target: (p) => p.getByRole("row", { name: /Late refund with DRI approval/ }), act: (p) => p.getByRole("row", { name: /Late refund with DRI approval/ }).click() },
      { kw: "Then", text: "I read what changes in plain language", target: (p) => p.getByRole("list", { name: "Plain language diff" }) },
      { kw: "When", text: "I run sandbox tests and the replay", target: (p) => p.getByTestId("run-checks"), act: (p) => p.getByTestId("run-checks").click() },
      { kw: "Then", text: "the replay shows 37 of the last 412 refund conversations would change", target: (p) => p.getByTestId("impact-summary") },
      { kw: "And", text: "it is C3, so it now waits for the L1 DRI", target: (p) => p.getByText(/Why this needs/).locator("xpath=ancestor::section") },
    ],
  },
  {
    id: "l2-view-as", chapter: "L2", feature: "Governance", title: "See exactly what an agent can reach",
    persona: "h-sec", why: "Access rules live in the graph, so you can check any agent or person before they act.",
    steps: [
      { kw: "Given", text: "I am Tharindu, security officer, on the knowledge graph", as: "h-sec", go: "/l2/graph", target: (p) => p.getByTestId("graph-canvas") },
      { kw: "When", text: "I choose “View as Care Agent”", target: (p) => p.getByRole("combobox", { name: "View as" }), act: async (p) => { await p.getByRole("combobox", { name: "View as" }).click(); await p.getByRole("option", { name: "View as Care Agent" }).click(); } },
      { kw: "Then", text: "locked nodes and edges show the exact reason", target: (p) => p.getByTestId("locked-edges") },
    ],
  },
  {
    id: "l2-denied", chapter: "L2", feature: "Governance", title: "Investigate a denied action",
    persona: "h-sec", why: "Security binds at the moment of action, and every allow or deny is logged with its rule.",
    steps: [
      { kw: "Given", text: "I open Security and access", go: "/l2/security", target: tableNamed("Invocation decision log") },
      { kw: "Then", text: "the Care Agent's refund attempt was denied by rule sr-refund-tool", target: (p) => p.getByRole("row", { name: /billing\.refund \(LKR 12,000\)/ }) },
      { kw: "And", text: "the Security Sentinel's proposed grant waits for two L1 approvals", target: (p) => p.getByText("Proposed by the Security Sentinel").locator("xpath=ancestor::section") },
    ],
  },
  {
    id: "l2-conflict", chapter: "L2", feature: "Governance", title: "Resolve a knowledge conflict",
    persona: "h-ks", why: "When new facts collide with old ones, the Librarian proposes one change that fixes everything that depends on them.",
    steps: [
      { kw: "Given", text: "I am Dilini, knowledge steward, in the ground truth vault", as: "h-ks", go: "/l2/vault", target: (p) => p.getByTestId("librarian-lib-refund-window") },
      { kw: "When", text: "I ask the Librarian to propose a resolution", target: (p) => p.getByTestId("propose-lib-refund-window"), act: (p) => p.getByTestId("propose-lib-refund-window").click() },
      { kw: "Then", text: "one change request updates the policy and every dependent", target: (p) => p.getByRole("table", { name: "Structured diff" }) },
      { kw: "When", text: "I run the checks", target: (p) => p.getByTestId("run-checks"), act: (p) => p.getByTestId("run-checks").click() },
      { kw: "Then", text: "ground truth changes are C3 and wait for the L1 DRI", target: (p) => p.getByText("awaiting approval").first() },
    ],
  },
  {
    id: "l2-time-travel", chapter: "L2", feature: "Governance", title: "Travel in time through a policy",
    persona: "h-ks", why: "You can answer “what was true then” and “what did we believe then”, for any date.",
    steps: [
      { kw: "Given", text: "I open the refund window policy", go: "/l2/policies/refund-window", target: (p) => p.getByRole("list", { name: "Policy versions" }) },
      { kw: "Then", text: "freshness signals warn that the policy is drifting", target: (p) => p.getByText("Freshness signals").locator("xpath=ancestor::section") },
      { kw: "When", text: "I move the “as of” slider back in time", target: (p) => p.getByRole("slider", { name: "As of date" }), act: async (p) => { await p.getByRole("slider", { name: "As of date" }).focus(); await p.keyboard.press("Home"); for (let i = 0; i < 6; i++) await p.keyboard.press("PageUp"); }, shot: "after" },
      { kw: "Then", text: "I see what was true then and what the system believed then", target: (p) => p.getByTestId("true-then").locator("xpath=..") },
    ],
  },
  {
    id: "l2-edit-skill", chapter: "L2", feature: "Governance", title: "Improve a skill safely",
    persona: "h-aiops", why: "Main never changes directly. Every edit is a draft on a sandbox branch with its own change request.",
    steps: [
      { kw: "Given", text: "skills sorted by conformance, weakest first", as: "h-aiops", go: "/l2/skills", target: tableNamed("Skills") },
      { kw: "When", text: "I open “Refund inside policy”", target: (p) => p.getByRole("row", { name: /Refund inside policy/ }), act: (p) => p.getByRole("row", { name: /Refund inside policy/ }).click() },
      { kw: "And", text: "I change step 2", target: (p) => p.getByLabel("Step 2 text"), act: (p) => p.getByLabel("Step 2 text").fill("Check window, threshold and plan type"), shot: "after" },
      { kw: "And", text: "I save it as a draft on a sandbox branch", target: role("Save as draft on a sandbox branch"), act: (p) => p.getByRole("button", { name: "Save as draft on a sandbox branch" }).click() },
      { kw: "Then", text: "a change request opens with a before and after diff", target: (p) => p.getByRole("table", { name: "Structured diff" }) },
    ],
  },
  {
    id: "l2-experiment", chapter: "L2", feature: "Governance", title: "Run a website experiment",
    persona: "h-aiops", why: "Friction found in Microsoft Clarity becomes a tested experiment, and every result is kept as learning.",
    steps: [
      { kw: "Given", text: "the Website UX loop: sensor, policy, tool, gate, learning", go: "/l2/loops/loop-website", target: (p) => p.getByLabel("Website UX loop canvas") },
      { kw: "And", text: "Clarity found 312 rage clicks on the pricing toggle", target: (p) => p.getByTestId("experiment-exp-pricing-toggle") },
      { kw: "When", text: "I preview it on a sandbox branch", target: (p) => p.getByRole("button", { name: /Preview on a sandbox branch/ }), act: (p) => p.getByRole("button", { name: /Preview on a sandbox branch/ }).click() },
      { kw: "And", text: "I start the A/B experiment", target: (p) => p.getByRole("button", { name: /Start A\/B experiment/ }), act: (p) => p.getByRole("button", { name: /Start A\/B experiment/ }).click() },
      { kw: "And", text: "I conclude it", target: role("Conclude"), act: (p) => p.getByRole("button", { name: "Conclude" }).click() },
      { kw: "When", text: "I keep and ship the winner", target: (p) => p.getByRole("button", { name: /Keep and ship/ }), act: (p) => p.getByRole("button", { name: /Keep and ship/ }).click() },
      { kw: "Then", text: "the learning is recorded and the pricing change goes to L1", target: (p) => p.getByTestId("experiment-exp-pricing-toggle") },
    ],
  },
  {
    id: "l2-plant", chapter: "L2", feature: "Governance", title: "Plant a sensor on the website",
    persona: "h-aiops", why: "Click any element of the site to decide what to track. The output is a reviewed tracking plan.",
    steps: [
      { kw: "Given", text: "I open Sensors and choose Sensor planting", go: "/l2/sensors", target: (p) => p.getByRole("tab", { name: /Sensor planting/ }), act: (p) => p.getByRole("tab", { name: /Sensor planting/ }).click() },
      { kw: "When", text: "I click the refunds FAQ in the website preview", target: (p) => p.getByRole("button", { name: /Attach a sensor to FAQ: Refund policy/ }), act: (p) => p.getByRole("button", { name: /Attach a sensor to FAQ: Refund policy/ }).click() },
      { kw: "And", text: "I review the event name and privacy flags, then add it", target: role("Add to tracking plan"), act: (p) => p.getByRole("button", { name: "Add to tracking plan" }).click() },
      { kw: "Then", text: "it appears in the tracking plan", target: (p) => p.getByTestId("tracking-plan") },
    ],
  },
  {
    id: "l2-readiness", chapter: "L2", feature: "Governance", title: "Find missing evidence before a deadline",
    persona: "h-ks", why: "The brain notices gaps 21 days early and asks the right person, long before a filing is due.",
    steps: [
      { kw: "Given", text: "I open the readiness scheduler", as: "h-ks", go: "/l2/readiness", target: (p) => p.getByTestId("run-scheduler") },
      { kw: "When", text: "I run the scheduler", target: (p) => p.getByTestId("run-scheduler"), act: (p) => p.getByTestId("run-scheduler").click() },
      { kw: "Then", text: "each gap gets an action: dispatch an agent, ask the DRI, or request a source", target: (p) => p.getByTestId("gaps") },
    ],
  },
  {
    id: "l2-knowledge", chapter: "L2", feature: "Governance", title: "Know what the brain knows",
    persona: "h-ks", why: "Library, resolver and templates show the documents, routing and contracts behind every answer.",
    steps: [
      { kw: "Given", text: "the Library lists every document with sensitivity and retention", go: "/l2/library", target: tableNamed("Documents") },
      { kw: "And", text: "the Resolver routes each event to an agent and skill, proven by trigger evals", go: "/l2/resolver", target: tableNamed("Resolver rules") },
      { kw: "And", text: "Templates define what each agent must bring back, from which sensors", go: "/l2/templates", target: (p) => p.locator("main section").first() },
    ],
  },
  {
    id: "l2-rollback", chapter: "L2", feature: "Governance", title: "Roll back safely",
    persona: "h-aiops", why: "Like git for the company: any commit can be reverted, and you see the impact first.",
    steps: [
      { kw: "Given", text: "I open the commits on main", as: "h-aiops", go: "/l2/versioning", target: (p) => p.getByRole("tab", { name: "Commits on main" }), act: (p) => p.getByRole("tab", { name: "Commits on main" }).click() },
      { kw: "When", text: "I choose “Roll back” on an older commit", target: (p) => p.getByRole("button", { name: /Roll back/ }).nth(3), act: (p) => p.getByRole("button", { name: /Roll back/ }).nth(3).click() },
      { kw: "Then", text: "I see every commit that would revert, before anything happens", target: (p) => p.getByRole("dialog"), after: (p) => p.getByRole("button", { name: "Cancel" }).click() },
    ],
  },

  // ------------------------------------------------------------ L1
  {
    id: "l1-overview", chapter: "L1", feature: "Command", title: "See the business at a glance",
    persona: "h-founder", why: "One view of every cluster: autonomy, risk, money at stake, and where the brain is still blind.",
    steps: [
      { kw: "Given", text: "I am Nadeesha, the founder, on the Brain overview", as: "h-founder", go: "/l1", target: (p) => p.locator("main .grid").first() },
      { kw: "Then", text: "each cluster shows health, autonomy, escalations and cost", target: (p) => p.getByRole("heading", { name: "Clusters" }).locator("xpath=..") },
      { kw: "And", text: "the legibility map shows which activities are not yet sensed, skilled, governed or reported", target: (p) => p.getByText("Legibility map").locator("xpath=ancestor::section") },
    ],
  },
  {
    id: "l1-digest", chapter: "L1", feature: "Command", title: "Read the morning digest",
    persona: "h-founder", why: "Overnight, the Quality Supervisor reviews every run, fixes routine issues and drafts the rest.",
    steps: [
      { kw: "Given", text: "I open the morning digest", go: "/l1/digest", target: h1 },
      { kw: "Then", text: "C0 and C1 fixes were applied automatically and logged", target: (p) => p.getByTestId("digest-applied") },
      { kw: "And", text: "bigger changes were drafted and wait for a decision", target: (p) => p.getByTestId("digest-drafted") },
    ],
  },
  {
    id: "l1-approve", chapter: "L1", feature: "Command", title: "Approve a new skill as the DRI",
    persona: "h-hcs", why: "Approval weight follows criticality: routine work flows, consequential work stops for the right person.",
    steps: [
      { kw: "Given", text: "I am Ishara, the DRI for refunds, in my approvals", as: "h-hcs", go: "/l1/approvals", target: (p) => p.getByRole("list", { name: "Approvals" }) },
      { kw: "When", text: "I open the new late refund skill", target: (p) => p.getByRole("link", { name: /Late refund with DRI approval/ }), act: (p) => p.getByRole("link", { name: /Late refund with DRI approval/ }).click() },
      { kw: "Then", text: "I see the diff, the replay, the tests and why it needs me", target: (p) => p.getByTestId("impact-summary") },
      { kw: "When", text: "I approve and merge to Production", target: (p) => p.getByTestId("approve"), act: (p) => p.getByTestId("approve").click() },
      { kw: "Then", text: "the skill is live, and the Refund Agent uses it from now on", target: (p) => p.getByText(/Merged .* Live in Production/).first() },
    ],
  },
  {
    id: "l1-two-person", chapter: "L1", feature: "Command", title: "Two person rule for critical changes",
    persona: "h-hcs", why: "C4 changes such as new agent capabilities always need two different L1 approvers.",
    steps: [
      { kw: "Given", text: "a C4 grant proposed by the Security Sentinel", go: "/l1/approvals/apr-sentinel-grant", target: (p) => p.getByRole("list", { name: "Plain language diff" }) },
      { kw: "When", text: "I approve it as the first approver", target: (p) => p.getByTestId("approve"), act: (p) => p.getByTestId("approve").click() },
      { kw: "Then", text: "it still needs a second, different L1 approver", target: (p) => p.getByRole("note") },
      { kw: "When", text: "Nadeesha approves as the second L1", as: "h-founder", go: "/l1/approvals/apr-sentinel-grant", target: (p) => p.getByTestId("approve"), act: (p) => p.getByTestId("approve").click() },
      { kw: "Then", text: "the grant is merged and the Care Agent may refund up to LKR 10,000", target: (p) => p.getByText(/Merged .* Live in Production/).first() },
    ],
  },
  {
    id: "l1-entity", chapter: "L1", feature: "Command", title: "Protect the legal entity",
    persona: "h-fd", why: "Tax, statutory, contract and renewal deadlines with readiness and missing proof. People still file.",
    steps: [
      { kw: "Given", text: "I am Ruwan, finance director, on Entity protection", as: "h-fd", go: "/l1/entity", target: (p) => p.getByRole("img", { name: /Obligation timeline/ }) },
      { kw: "Then", text: "each obligation shows readiness, missing evidence, countdown and DRI", target: (p) => p.getByTestId("obligation-ob-vat-sep") },
      { kw: "And", text: "the risk register lists what could go wrong and who owns it", target: (p) => p.getByText("Risk register").locator("xpath=ancestor::section") },
    ],
  },
  {
    id: "l1-evidence", chapter: "L1", feature: "Command", title: "Provide evidence or grant access",
    persona: "h-fd", why: "Upload proof, or grant a data source with a clear scope, retention and revoke path.",
    steps: [
      { kw: "Given", text: "the brain asked me for the September VAT evidence", go: "/l1/evidence", target: (p) => p.locator('[data-testid^="evidence-"]').filter({ hasText: "Input VAT invoices" }) },
      { kw: "When", text: "I look at granting the finance inbox instead", target: (p) => p.locator('[data-testid^="evidence-"]').filter({ hasText: "Input VAT invoices" }).getByRole("button", { name: /Grant a data source/ }), act: (p) => p.locator('[data-testid^="evidence-"]').filter({ hasText: "Input VAT invoices" }).getByRole("button", { name: /Grant a data source/ }).click() },
      { kw: "Then", text: "I see scope, retention, agents and how to revoke before granting", target: (p) => p.getByRole("dialog"), after: (p) => p.getByRole("button", { name: "Cancel" }).click() },
      { kw: "When", text: "I upload the invoices and the bank statement instead", target: (p) => p.getByRole("list").filter({ hasText: "Input VAT invoices" }).first(), act: async (p) => { for (const item of ["Input VAT invoices", "Bank statement"]) await p.locator('[data-testid^="evidence-"]').filter({ hasText: item }).filter({ hasText: "VAT return" }).locator('input[type="file"]').setInputFiles({ name: `${item}.pdf`, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") }); await p.waitForTimeout(800); }, shot: "after" },
      { kw: "Then", text: "the VAT return is ready: every item has a fact with provenance", go: "/l1/entity", target: (p) => p.getByTestId("obligation-ob-vat-sep") },
    ],
  },
  {
    id: "l1-analytics", chapter: "L1", feature: "Command", title: "Follow progress",
    persona: "h-founder", why: "Runs, autonomy per cluster, loop performance, experiments and template completion.",
    steps: [
      { kw: "Given", text: "I open Progress and analytics", as: "h-founder", go: "/l1/analytics", target: (p) => p.locator("main section").first() },
      { kw: "Then", text: "I compare loops and experiments in one place", target: (p) => p.getByText("Loop performance").locator("xpath=ancestor::section") },
    ],
  },
  {
    id: "l1-audit", chapter: "L1", feature: "Command", title: "Audit everything that happened",
    persona: "h-founder", why: "Every action by any human or agent, read only, filterable by actor, object, environment and criticality.",
    steps: [
      { kw: "Given", text: "I open the audit trail for the CUS-1042 refund story", go: "/l1/audit?correlation=conv%3Aconv-1042", target: tableNamed("Audit events") },
      { kw: "Then", text: "I see takeover, Skillify, tests, approval and merge in order, with who did each", target: tableNamed("Audit events") },
    ],
  },

  // ------------------------------------------------------------ Research
  {
    id: "research", chapter: "research", feature: "Research Console", title: "Monitor research metrics",
    persona: "h-research", why: "A separate, read only console for the research program. It can be removed without touching the product.",
    steps: [
      { kw: "Given", text: "I am the research analyst", as: "h-research", go: "/research/skills", target: h1 },
      { kw: "Then", text: "metrics for skills, policies, security and integration are labelled SAMPLE", target: (p) => p.locator("main ul").first() },
      { kw: "And", text: "sample values can never be exported as results", target: (p) => p.getByText(/Sample values can never be exported/) },
    ],
  },
];
