# finebrain

## Design principle: calm, spacious, few words

This is a core value of the product. Every screen must feel calm and be understood at a glance.

- **Few words per screen.** Short labels (1 to 3 words). Put detail behind a click, never on the first view.
- **One thing at a time.** When there is a list of rich items (cases, steps, proposals), show one as a card with Next and Back, not a long list.
- **Spacious.** Generous padding and gaps. Readable sizes: body 15px or more, nothing important below 12px.
- **Show only what matters now.** Hide empty or finished things, collapse the rest, highlight what is changing.
- **One accent colour**, used only for "this is happening now" or the main action.

When a design choice trades clarity for density, choose clarity.

## File organization

Every file lives in a folder that matches its job. No loose files at the repo root or the top of `backend/` or `frontend/`.

| Kind of file | Folder |
|---|---|
| App code (API, pipeline stages, contracts) | `backend/app/` |
| One-off dev scripts (key checks, smoke tests) | `backend/scripts/` |
| Automated tests (pytest) | `backend/tests/` |
| Sample and fixture data | `backend/samples/` |
| Design docs and guides | `Docs/` |

- Only project config stays at the top of `backend/`: `pyproject.toml`, `uv.lock`, `README.md`, `.env`, `.env.example`, `.gitignore`, `.python-version`.
- If a new file fits no folder above, ask before creating a new folder.
- Scratch and temporary files go in the session scratchpad, never in the repo.
