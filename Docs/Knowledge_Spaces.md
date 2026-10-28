# Knowledge spaces

Status: idea, not built. Written 2026-10-28 so we can develop it later.

## Why

The brain will serve many platforms (for example Finebase Labs and Finebase Platform). Today every document and connection carries a cluster label, but nothing filters knowledge by it when a chat answers, and no screen asks which platform something belongs to. Uploads all go to one seeded cluster. (Found by searching the code, not a full audit.)

## The idea

A **knowledge space** is a named container for knowledge, one per platform. It is a first-class object: everything that holds or uses knowledge belongs to a space, and access is checked against it.

| Rule | Meaning |
|---|---|
| One home | Every document, fact, policy, skill, workflow, template and connection belongs to exactly one space |
| Bound readers | A chat, agent or workflow reads only the spaces it is bound to (one or more) |
| Private by default | Nothing crosses spaces unless a link says so |
| Explicit links | Linking two spaces is a reviewed change with an owner, like any other change |
| Access checks space | The access check looks at space as well as tier and capability |

## Ask the Brain

| Need | Design |
|---|---|
| Focus on several platforms | A row of tick boxes, one per space. Tick one or many |
| Focus on one platform | Tick one. The answer cites only that space |
| Not sure which | Ask in plain words ("which platform is this about?"), or let the brain suggest a tick and show it, so the person can change it |
| Run through a workflow | The workflow brings its own spaces. The person sees them and can narrow, never widen |
| Show what was used | Every answer says which spaces it read |
| Nothing ticked | Default to the person's usual spaces, shown plainly. Never silently all |

## Adding things

Adding a skill, workflow, policy, template, document or connection starts with one question: **which platform?** It is a required, prefilled choice (the current filter), never hidden.

## One platform filter everywhere

A single platform switcher in the top bar, next to Tenant and Cluster. Tick one or many. Every list follows it.

| Screen | Follows the filter |
|---|---|
| Skills, policies, templates, resolver | Yes |
| Workflow Studio, versions | Yes |
| Knowledge graph, vault, library | Yes |
| Chat history, Ask the Brain history | Yes |
| Agents and fleet | Yes |
| Security (decisions, rules, data sources) | Yes |
| Audit trail, approvals, trends | Yes |

Each item also shows its platform as a short chip. A list across many platforms groups by platform.

## Linking spaces

| Question | Starting answer |
|---|---|
| Who may link | A leader, through a change request that needs approval |
| What a link shares | Read access to named parts (for example "refund policy"), not everything |
| Direction | One way unless both are approved |
| Ending a link | Immediate, with the same confirm step as revoking a data source |
| Seen where | Security, Rules, and on both spaces |

## Parts of the system that change

| Area | Change |
|---|---|
| Data | A `space_id` on every knowledge record, with a migration that puts today's data in a first space |
| Retrieval | Filter by the bound spaces on the key lookup, never by scanning |
| Access (S7, OPA) | Add space to the input and the rules, with a deny reason that names it |
| Connections | A chat or inbox connection is bound to spaces when it is set up |
| Studio | Items carry a space. The review shows what a change touches |
| Console | The top-bar filter, tick boxes in Ask the Brain, chips, and grouping |
| Tests | Two spaces side by side: no leak, a link works, ending it stops it |

## Open questions

- Can one skill or workflow belong to more than one space, or is it copied?
- Are people and roles global, or set per space?
- Does the audit trail span spaces for a leader?
- What is the tenant-level knowledge, if any, that every space may read (for example company policy)?
- How does the learning loop decide which space a new fact belongs to?

## Suggested order

1. Space record and migration of today's data into one space.
2. Retrieval and access filter by space, with the no-leak tests.
3. Space field when adding things, and chips.
4. Top-bar platform filter across lists.
5. Ask the Brain tick boxes and "which platform" asking.
6. Linking spaces, with approval.
7. Real-infrastructure tests, many workers, and a volume run, per the stage-done bar in CLAUDE.md.
