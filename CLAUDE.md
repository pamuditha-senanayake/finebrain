# finebrain

## File organization

Every file lives in a folder that matches its job. No loose files at the repo root or the top of `backend/` or `frontend/`.

| Kind of file | Folder |
|---|---|
| App code (API, pipeline stages, contracts) | `backend/app/` |
| One-off dev scripts (key checks, smoke tests) | `backend/scripts/` |
| Sample and fixture data | `backend/samples/` |
| Design docs and guides | `Docs/` |

- Only project config stays at the top of `backend/`: `pyproject.toml`, `uv.lock`, `README.md`, `.env`, `.env.example`, `.gitignore`, `.python-version`.
- If a new file fits no folder above, ask before creating a new folder.
- Scratch and temporary files go in the session scratchpad, never in the repo.
