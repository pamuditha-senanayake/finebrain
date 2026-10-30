# Living memory: screens and states

Date: 2026-10-30. Stage 2 of `CB_Living_Memory_Build_Plan.md`. Design source: `CB_Living_Memory_Architecture.md`.

## Who it is for and what they want

An owner or steward opens it to answer one question: **is the brain still true?** First they want to know where work happens. Then whether anything is drifting. Then they want the proof: the traces.

## Where it lives

- **Living memory** at `/l1/memory`, a nav item right under Brain overview. Brain overview stays as it is for now.
- **From traces**, a new tab in Skills at `/l2/skills`.
- **Drift**, shown in the policy registry's Freshness column at `/l2/policies`.

## Flow

| Step | What they see | What they can do |
|---|---|---|
| 1. Glance | The whole page is one globe, divided into 8 coloured areas like countries. Areas facing you carry a label with their name and trace count. A small panel at the top right holds four figures: traces this week, patterns, drift, waiting. A legend at the bottom left lists every area | Drag to turn the globe. Hover an area to lift it. Click it, or its legend row, to turn it to the front and open its card |
| 2. Area card | One area at a time, with Back and Next. It shows traces this week, patterns used against the budget (12 of 50), skills (authored and from traces), and three drift lines (skill, policy, security) | "See traces", "See drift", or close |
| 3. Traces | A list for that area, newest first. Each row has the subject, pattern, normal or surprise, the policy check, and when | Filter by area or by flag (surprise, outside policy, drift). Open one |
| 4. Trace | A numbered step line: input, area and pattern, each step with its why, policy version, skill version, each access decision, outcome | Back to the list. Open the run, or open in To review if it was a surprise |
| 5. Drift | One drift at a time, with Back and Next. It shows the kind, what drifted, usual against latest, the draft fix, and a numbered step line of its state: detected, sent to L1, waiting for approval, approved, resolved | Open the evidence traces, or open in To review |

In From traces, one skill draft is shown at a time: its name, area, steps, how many traces support it, the share with the same outcome, the follow rate, and its review state.

## Words

The page has few words. These are the only labels on the first view: Living memory, Traces this week, Patterns, Drift, Waiting, and the area names. Everything else sits behind a click.

## Colour

Each area has one fixed colour, which the draw.io diagram also uses. The accent colour marks only drift and surprises, because those are what is happening now. "No drift" is plain grey text, never green confetti.

## States

| State | What shows |
|---|---|
| Loading | The brain's dots fade in. The figures show skeleton bars |
| Empty (no traces yet) | The brain is shown dim, with one line: "No traces yet. They appear after the first run." It links to Connect |
| Area with no traces | The card says "Quiet this week". It still shows skills and drift |
| Error | "Couldn't load the living memory." with a Try again button. The brain stays dim |
| Sample data | A "Sample" badge next to the title, with a tooltip: "Made-up data until the live connection is built" |
| Reduced motion, or no WebGL | A still 2D dot map with the same areas and callouts. Nothing moves |
| Disabled action | Each one says why, for example "Send for review: you need the L2 steward role" |

## Accessibility

- Every area can be reached with Tab, in a fixed order. Enter opens its card.
- The canvas has a text twin: a visually hidden list of areas with their counts.
- Nothing relies on colour alone. Drift shows a count and an icon as well.
- Contrast meets AA in both themes.

## API contracts

Zod schemas live in `frontend/contracts/memory.ts`. Paths are relative to `/api/t/{tenant}/`.

| Path | Returns |
|---|---|
| `memory` | `MemoryMap`: every area with its counts, plus the totals |
| `memory/areas/:key` | `AreaDetail`: the area, its patterns, its drift items |
| `memory/traces?area=&flag=&cursor=` | `TracePage`: trace summaries, newest first, 25 per page |
| `memory/traces/:id` | `TraceDetail`: the full trace from start to end |
| `memory/drifts?area=&kind=` | A list of `DriftItem` |
| `memory/skills` | A list of `ExtractedSkill` |
