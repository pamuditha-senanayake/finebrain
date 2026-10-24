# finebrain

## Design principle: calm, spacious, few words

This is a core value of the product. Every screen must feel calm and be understood at a glance.

- **Few words per screen.** Short labels (1 to 3 words). Put detail behind a click, never on the first view.
- **One thing at a time.** When there is a list of rich items (cases, steps, proposals), show one as a card with Next and Back, not a long list.
- **Spacious.** Generous padding and gaps. Readable sizes: body 15px or more, nothing important below 12px.
- **Show only what matters now.** Hide empty or finished things, collapse the rest, highlight what is changing.
- **One accent colour**, used only for "this is happening now" or the main action.

When a design choice trades clarity for density, choose clarity.

## UI and UX standards: design it, never just drop a control in

Every screen must look and work like a professional product. Needing an input is not a reason to place a bare input. Design the whole interaction first, then build it.

- **Follow established UI/UX standards.** Use known patterns (Nielsen's heuristics, WCAG 2.2 AA, platform conventions) and the components in `components/ui` and `components/brain`. No one-off controls.
- **Design the flow, not the field.** Before building, answer: what is the person trying to do, what do they need to know first, what comes next, and how do they recover from a mistake.
- **Starting something gets a proper entry.** Use a clear primary button that opens a dialog or a guided path (choose a type, name it, then continue). Never a lone text box with "+ New".
- **Chat looks like chat.** Use bubbles, a multi-line composer (Enter sends, Shift+Enter adds a line), auto-scroll to the newest message, and a visible thinking state. Never a one-line box at the bottom of a card.
- **Progress looks like progress.** Show steps as a numbered step line with done, current and upcoming states. Steps that are not buttons must not look like buttons.
- **The next action is always obvious.** Put Back on the left and the next step on the right, named for what it does ("Next: paste their answer"). Never vague labels like "They delivered".
- **Every button says what happens and why.** "Copy request for their coding agent", not "Copy brief". Add one line of context when the reason is not obvious.
- **Group things the way people think.** Group by platform, owner or purpose. Never one flat list of mixed kinds, and never two pages for the same idea (for example, Connections and Sensors).
- **Every state is designed.** Cover loading, empty (with a way forward), error (plain words and how to fix), success and disabled (say why).
- **Ask for the least.** Let people paste one answer and have the system extract the parts. Do not show three separate boxes when one will do. Prefill what is already known.
- **Accessible by default.** Every control has a visible label or `aria-label`. Everything is reachable by keyboard with a visible focus state. Contrast is AA or better. Nothing relies on colour alone.
- **Responsive and contained.** Layouts work from phone to wide desktop, nothing spills out of its card, and there is no horizontal scroll.
- **Check it in the browser before calling it done.** Click through it as a first-time user and look at every state. If any part would confuse someone who has never seen it, it is not finished.

## Coding style

- Every time you write code, use the skills `/anthropic-skills:zed-coding` and `/anthropic-skills:zed-coding-files`.
- Files stay at 150 lines or less. If going over is truly the best way, ask first and give the reason in 30 words or less.

## File organization

Every file lives in a folder that matches its job. No loose files at the repo root or the top of `backend/` or `frontend/`.

| Kind of file | Folder |
|---|---|
| App code (API, pipeline stages, contracts) | `backend/app/` |
| One-off dev scripts (key checks, smoke tests) | `backend/scripts/` |
| Automated tests (pytest) | `backend/tests/` |
| Hands-on demos (edit the input, run, read the output) | `backend/demos/` |
| Local infra (Docker Compose) | `backend/infra/` |
| Sample and fixture data | `backend/samples/` |
| Design docs and guides | `Docs/` |

- Only project config stays at the top of `backend/`: `pyproject.toml`, `uv.lock`, `README.md`, `.env`, `.env.example`, `.gitignore`, `.python-version`.
- If a new file fits no folder above, ask before creating a new folder.
- Scratch and temporary files go in the session scratchpad, never in the repo.

## Commits and pull requests

Do not add Claude attribution to commit messages or pull request descriptions: no `Co-Authored-By` line, no `Claude-Session` line, no "Generated with" line.
