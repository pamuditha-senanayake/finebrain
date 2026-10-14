# Company Brain User Guide (BDD scenarios)

Every use case of the Company Brain console, written as Given, When, Then scenarios. The guide video plays these same scenarios on the real app (`video/guide/company_brain_user_guide.mp4`). The scenarios live in `frontend/scripts/guide/scenarios.mjs`; this file is generated from them by `node scripts/guide/write-bdd.mjs`.

## What Company Brain is

A governed layer where AI agents run company operations (customer care, refunds, billing, sales, scheduling, website changes, tax readiness) using company knowledge, under policies and security that people control.

| Tier | Who | What you do there |
|---|---|---|
| L1 Command | Founders, directors, DRIs | Follow progress and risk, approve high criticality changes, provide evidence, protect the legal entity |
| L2 Governance | Stewards and supervisor agents | Author and test skills, policies, security, templates and knowledge before anything ships |
| L3 Operations floor | Worker agents and operators | Agents do the work. Operators watch live, inspect runs, take over and Skillify |

Every function is a loop: **sensor** (notices what happened), **policy** (decides what is allowed), **tool** (does the work), **quality gate** (checks the result), **learning** (improves overnight).

## Where to start

Pick your persona from the menu in the top right of any screen. Higher tiers can look down, never up.

| Persona | Role | Tier | Start here |
|---|---|---|---|
| Nadeesha Perera | Founder | L1 | Brain overview, then Morning digest |
| Ruwan Jayasinghe | Finance Director | L1 | Entity protection, then Evidence requests |
| Ishara Fernando | Head of Customer Success | L1 | Approvals |
| Dilini Wickramasinghe | Knowledge Steward | L2 | Ground truth vault (librarian queue) |
| Kasun Bandara | AI Operations Lead | L2 | Versioning (change requests) |
| Tharindu Silva | Security Officer | L2 | Security and access |
| Amaya Gunawardena | Customer Care Operator | L3 | Escalations, then Live conversations |
| Research Analyst | Research program | L2 | Research Console |

## How to read a scenario

| Keyword | Meaning |
|---|---|
| Given | The situation, the screen and who you are |
| When | What you do |
| Then | What you should see |
| And | One more of the line above |

Criticality decides who approves: C0 automatic, C1 L2 supervisor agent, C2 L2 steward, C3 the L1 DRI, C4 two L1 approvers.

## Getting started

### 1. Pick who you are and open your home

**Persona:** Nadeesha Perera, Founder (L1) · **Screen:** `/`

**Why it matters:** Each person sees the tier that matches their job. Higher tiers can look down, never up.

```gherkin
Feature: Getting started

  Scenario: Pick who you are and open your home
    Given I open Company Brain
    When I open the persona menu in the top right
    And I choose Ishara Fernando, Head of Customer Success
    Then I land on L1 Command, the leadership home
    And the red band always tells me I am looking at Production
```

### 2. Jump anywhere with the command palette

**Persona:** Ishara Fernando, Head of Customer Success (L1) · **Screen:** `/l1`

**Why it matters:** Press ⌘K from any screen to find agents, skills, policies, approvals or runs.

```gherkin
Feature: Getting started

  Scenario: Jump anywhere with the command palette
    Given I am on any screen
    When I open the palette with ⌘K
    And I type “Refund Agent”
    Then I open the agent straight from the results
    And I see its job description: sensors, skills, policies, capabilities
```

### 3. Ask the Brain a question

**Persona:** Ishara Fernando, Head of Customer Success (L1) · **Screen:** `/l1`

**Why it matters:** Answers come only from facts you may see, each with its source and when it is true.

```gherkin
Feature: Getting started

  Scenario: Ask the Brain a question
    When I click Ask the Brain
    And I ask “What is our refund window?”
    Then I get a plain answer with numbered citations
    And each citation shows when the fact is true in the world
```

## L3 Operations floor

### 4. Watch the agent fleet

**Persona:** Amaya Gunawardena, Customer Care Operator (L3) · **Screen:** `/l3`

**Why it matters:** Agents do the work through APIs. This is where people watch them live and step in.

```gherkin
Feature: Operations floor

  Scenario: Watch the agent fleet
    Given I am Amaya, a customer care operator
    Then I see every agent with live status, queue, errors and cost
    When I switch to the grid view
    Then a moving orb means an agent is working right now
```

### 5. Inspect any run step by step

**Persona:** Amaya Gunawardena, Customer Care Operator (L3) · **Screen:** `/l3/runs`

**Why it matters:** Every decision is traceable: what the agent read, what it decided, which checks it passed.

```gherkin
Feature: Operations floor

  Scenario: Inspect any run step by step
    Given I open Runs
    When I filter for customer CUS-1042
    And I open the refund run
    Then each step is labelled model judgment or deterministic call
    And the escalation says exactly why the agent stopped
```

### 6. Handle an escalation, then Skillify it

**Persona:** Amaya Gunawardena, Customer Care Operator (L3) · **Screen:** `/l3/escalations`

**Why it matters:** Never do one off work: the way a person solved a case becomes a reusable skill.

```gherkin
Feature: Operations floor

  Scenario: Handle an escalation, then Skillify it
    Given the escalations queue, sorted by risk and waiting time
    When I open the refund request from CUS-1042
    Then I see the transcript, the agent's reasoning and its proposed actions
    When I take over the conversation
    And I reply to the customer myself
    And I press Skillify
    Then my handling becomes a draft skill on a sandbox branch for L2 to test
```

### 7. Check the template board

**Persona:** Amaya Gunawardena, Customer Care Operator (L3) · **Screen:** `/l3/templates`

**Why it matters:** Templates are what each agent must bring back. Stale or partial ones stand out.

```gherkin
Feature: Operations floor

  Scenario: Check the template board
    Given I open the template board
    When I filter to stale templates
    Then I see which fields are old, who filled them and from which source
```

## L2 Governance

### 8. Test a draft skill before it goes live

**Persona:** Kasun Bandara, AI Operations Lead (L2) · **Screen:** `/l2/versioning`

**Why it matters:** Nothing goes live blind: sandbox tests and a replay of real runs come before any approval.

```gherkin
Feature: Governance

  Scenario: Test a draft skill before it goes live
    Given I am Kasun, AI operations lead, on Versioning
    When I open “New skill: Late refund with DRI approval”
    Then I read what changes in plain language
    When I run sandbox tests and the replay
    Then the replay shows 37 of the last 412 refund conversations would change
    And it is C3, so it now waits for the L1 DRI
```

### 9. See exactly what an agent can reach

**Persona:** Tharindu Silva, Security Officer (L2) · **Screen:** `/l2/graph`

**Why it matters:** Access rules live in the graph, so you can check any agent or person before they act.

```gherkin
Feature: Governance

  Scenario: See exactly what an agent can reach
    Given I am Tharindu, security officer, on the knowledge graph
    When I choose “View as Care Agent”
    Then locked nodes and edges show the exact reason
```

### 10. Investigate a denied action

**Persona:** Tharindu Silva, Security Officer (L2) · **Screen:** `/l2/security`

**Why it matters:** Security binds at the moment of action, and every allow or deny is logged with its rule.

```gherkin
Feature: Governance

  Scenario: Investigate a denied action
    Given I open Security and access
    Then the Care Agent's refund attempt was denied by rule sr-refund-tool
    And the Security Sentinel's proposed grant waits for two L1 approvals
```

### 11. Resolve a knowledge conflict

**Persona:** Dilini Wickramasinghe, Knowledge Steward (L2) · **Screen:** `/l2/vault`

**Why it matters:** When new facts collide with old ones, the Librarian proposes one change that fixes everything that depends on them.

```gherkin
Feature: Governance

  Scenario: Resolve a knowledge conflict
    Given I am Dilini, knowledge steward, in the ground truth vault
    When I ask the Librarian to propose a resolution
    Then one change request updates the policy and every dependent
    When I run the checks
    Then ground truth changes are C3 and wait for the L1 DRI
```

### 12. Travel in time through a policy

**Persona:** Dilini Wickramasinghe, Knowledge Steward (L2) · **Screen:** `/l2/policies/refund-window`

**Why it matters:** You can answer “what was true then” and “what did we believe then”, for any date.

```gherkin
Feature: Governance

  Scenario: Travel in time through a policy
    Given I open the refund window policy
    Then freshness signals warn that the policy is drifting
    When I move the “as of” slider back in time
    Then I see what was true then and what the system believed then
```

### 13. Improve a skill safely

**Persona:** Kasun Bandara, AI Operations Lead (L2) · **Screen:** `/l2/skills`

**Why it matters:** Main never changes directly. Every edit is a draft on a sandbox branch with its own change request.

```gherkin
Feature: Governance

  Scenario: Improve a skill safely
    Given skills sorted by conformance, weakest first
    When I open “Refund inside policy”
    And I change step 2
    And I save it as a draft on a sandbox branch
    Then a change request opens with a before and after diff
```

### 14. Run a website experiment

**Persona:** Kasun Bandara, AI Operations Lead (L2) · **Screen:** `/l2/loops/loop-website`

**Why it matters:** Friction found in Microsoft Clarity becomes a tested experiment, and every result is kept as learning.

```gherkin
Feature: Governance

  Scenario: Run a website experiment
    Given the Website UX loop: sensor, policy, tool, gate, learning
    And Clarity found 312 rage clicks on the pricing toggle
    When I preview it on a sandbox branch
    And I start the A/B experiment
    And I conclude it
    When I keep and ship the winner
    Then the learning is recorded and the pricing change goes to L1
```

### 15. Plant a sensor on the website

**Persona:** Kasun Bandara, AI Operations Lead (L2) · **Screen:** `/l2/sensors`

**Why it matters:** Click any element of the site to decide what to track. The output is a reviewed tracking plan.

```gherkin
Feature: Governance

  Scenario: Plant a sensor on the website
    Given I open Sensors and choose Sensor planting
    When I click the refunds FAQ in the website preview
    And I review the event name and privacy flags, then add it
    Then it appears in the tracking plan
```

### 16. Find missing evidence before a deadline

**Persona:** Dilini Wickramasinghe, Knowledge Steward (L2) · **Screen:** `/l2/readiness`

**Why it matters:** The brain notices gaps 21 days early and asks the right person, long before a filing is due.

```gherkin
Feature: Governance

  Scenario: Find missing evidence before a deadline
    Given I open the readiness scheduler
    When I run the scheduler
    Then each gap gets an action: dispatch an agent, ask the DRI, or request a source
```

### 17. Know what the brain knows

**Persona:** Dilini Wickramasinghe, Knowledge Steward (L2) · **Screen:** `/l2/library`

**Why it matters:** Library, resolver and templates show the documents, routing and contracts behind every answer.

```gherkin
Feature: Governance

  Scenario: Know what the brain knows
    Given the Library lists every document with sensitivity and retention
    And the Resolver routes each event to an agent and skill, proven by trigger evals
    And Templates define what each agent must bring back, from which sensors
```

### 18. Roll back safely

**Persona:** Kasun Bandara, AI Operations Lead (L2) · **Screen:** `/l2/versioning`

**Why it matters:** Like git for the company: any commit can be reverted, and you see the impact first.

```gherkin
Feature: Governance

  Scenario: Roll back safely
    Given I open the commits on main
    When I choose “Roll back” on an older commit
    Then I see every commit that would revert, before anything happens
```

## L1 Command

### 19. See the business at a glance

**Persona:** Nadeesha Perera, Founder (L1) · **Screen:** `/l1`

**Why it matters:** One view of every cluster: autonomy, risk, money at stake, and where the brain is still blind.

```gherkin
Feature: Command

  Scenario: See the business at a glance
    Given I am Nadeesha, the founder, on the Brain overview
    Then each cluster shows health, autonomy, escalations and cost
    And the legibility map shows which activities are not yet sensed, skilled, governed or reported
```

### 20. Read the morning digest

**Persona:** Nadeesha Perera, Founder (L1) · **Screen:** `/l1/digest`

**Why it matters:** Overnight, the Quality Supervisor reviews every run, fixes routine issues and drafts the rest.

```gherkin
Feature: Command

  Scenario: Read the morning digest
    Given I open the morning digest
    Then C0 and C1 fixes were applied automatically and logged
    And bigger changes were drafted and wait for a decision
```

### 21. Approve a new skill as the DRI

**Persona:** Ishara Fernando, Head of Customer Success (L1) · **Screen:** `/l1/approvals`

**Why it matters:** Approval weight follows criticality: routine work flows, consequential work stops for the right person.

```gherkin
Feature: Command

  Scenario: Approve a new skill as the DRI
    Given I am Ishara, the DRI for refunds, in my approvals
    When I open the new late refund skill
    Then I see the diff, the replay, the tests and why it needs me
    When I approve and merge to Production
    Then the skill is live, and the Refund Agent uses it from now on
```

### 22. Two person rule for critical changes

**Persona:** Ishara Fernando, Head of Customer Success (L1) · **Screen:** `/l1/approvals/apr-sentinel-grant`

**Why it matters:** C4 changes such as new agent capabilities always need two different L1 approvers.

```gherkin
Feature: Command

  Scenario: Two person rule for critical changes
    Given a C4 grant proposed by the Security Sentinel
    When I approve it as the first approver
    Then it still needs a second, different L1 approver
    When Nadeesha approves as the second L1
    Then the grant is merged and the Care Agent may refund up to LKR 10,000
```

### 23. Protect the legal entity

**Persona:** Ruwan Jayasinghe, Finance Director (L1) · **Screen:** `/l1/entity`

**Why it matters:** Tax, statutory, contract and renewal deadlines with readiness and missing proof. People still file.

```gherkin
Feature: Command

  Scenario: Protect the legal entity
    Given I am Ruwan, finance director, on Entity protection
    Then each obligation shows readiness, missing evidence, countdown and DRI
    And the risk register lists what could go wrong and who owns it
```

### 24. Provide evidence or grant access

**Persona:** Ruwan Jayasinghe, Finance Director (L1) · **Screen:** `/l1/evidence`

**Why it matters:** Upload proof, or grant a data source with a clear scope, retention and revoke path.

```gherkin
Feature: Command

  Scenario: Provide evidence or grant access
    Given the brain asked me for the September VAT evidence
    When I look at granting the finance inbox instead
    Then I see scope, retention, agents and how to revoke before granting
    When I upload the invoices and the bank statement instead
    Then the VAT return is ready: every item has a fact with provenance
```

### 25. Follow progress

**Persona:** Nadeesha Perera, Founder (L1) · **Screen:** `/l1/analytics`

**Why it matters:** Runs, autonomy per cluster, loop performance, experiments and template completion.

```gherkin
Feature: Command

  Scenario: Follow progress
    Given I open Progress and analytics
    Then I compare loops and experiments in one place
```

### 26. Audit everything that happened

**Persona:** Nadeesha Perera, Founder (L1) · **Screen:** `/l1/audit?correlation=conv%3Aconv-1042`

**Why it matters:** Every action by any human or agent, read only, filterable by actor, object, environment and criticality.

```gherkin
Feature: Command

  Scenario: Audit everything that happened
    Given I open the audit trail for the CUS-1042 refund story
    Then I see takeover, Skillify, tests, approval and merge in order, with who did each
```

## Research Console

### 27. Monitor research metrics

**Persona:** Research Analyst, Research program (L2) · **Screen:** `/research/skills`

**Why it matters:** A separate, read only console for the research program. It can be removed without touching the product.

```gherkin
Feature: Research Console

  Scenario: Monitor research metrics
    Given I am the research analyst
    Then metrics for skills, policies, security and integration are labelled SAMPLE
    And sample values can never be exported as results
```

## Why use Company Brain in an enterprise

| Benefit | What it means | Where you see it |
|---|---|---|
| Work finishes without people, safely | Agents resolve routine work inside their skills and capabilities | Brain overview, Fleet |
| Approval weight follows criticality | Routine changes flow, consequential ones stop for the right DRI, C4 needs two L1 approvers | Approvals |
| Nothing goes live blind | Sandbox tests, replay of real runs and a plain language diff before any approval | Versioning |
| Ground truth you can trust | Every fact has evidence, valid time, recorded time and a verifier; conflicts are caught | Ground truth vault, Policy registry |
| Security at the moment of action | Agents cannot exceed their capabilities or the person they act for; every decision is logged | Security and access, View as |
| Never do one off work | Skillify turns how a person handled a case into a tested, versioned skill | Live conversations |
| Protects the legal entity | Deadlines watched 21 days ahead, evidence requested early, scoped and revocable data grants | Entity protection, Evidence requests |
| Complete accountability | One named DRI per object and a read only audit trail of every action | Audit trail |
| Built for enterprise scale | Hundreds of agents and tens of thousands of runs, versioned and rollbackable like git | Scale Demo tenant |

All tenant data in the console is deterministic demo data. Dates, tax rules and amounts are samples, not legal or tax guidance.
