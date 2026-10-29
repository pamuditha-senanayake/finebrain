# Finebase HQ-2: the second live tenant

HQ-2 (`finebase-hq-2`) is a second real tenant, served by its own API process on port 8001, filled from the A1 to A11 list in `[FBL] Finebase Priorities.md`. Every name and number is made up. It adds data only: S1 to S15 are untouched.

## Run it

| Step | Command |
|---|---|
| Infra up (Postgres, S3 are needed) | `backend/scripts/dev_up.sh` |
| Regenerate sample files (only after editing `scripts/hq2_*.py`) | `cd backend && uv run python -m scripts.hq2_world` |
| Seed (safe to repeat) | `cd backend && uv run python -m scripts.seed_hq2` |
| Clear HQ-2 rows and seed again | `uv run python -m scripts.seed_hq2 --reset` |
| Serve | launch config `backend-hq2` (port 8001, `HQ_USE_CLAUDE=off`) and `frontend`; pick "Finebase HQ-2" in the top bar |
| Research screen | also run `backend` (port 8000): the Lab and its results live on HQ |

## What was changed in existing code

| File | Change |
|---|---|
| `backend/app/api/hq.py` | `HQ_TENANT_FILE` picks the tenant file (default HQ's); `topic_prefix()` gives HQ-2 its own Kafka topics. HQ behaves as before |
| `frontend/lib/flags.ts`, `lib/api/client.ts`, `lib/live/index.ts` | HQ-2 is a real tenant with its own API address (`NEXT_PUBLIC_API_BASE_URL_HQ2`, default `http://localhost:8001`) |
| `frontend/lib/store.ts`, `lib/mock/db.ts` | default persona and the tenant picker entry |
| four `features/*` files | "is a real tenant" now means any real tenant, not only HQ |
| `.claude/launch.json` | `backend-hq2` |

## What HQ-2 holds

| Area | Content |
|---|---|
| Platforms (12) | Slack, WhatsApp, Gmail, Zoom/Meet transcripts, Notion (paused, A11), GitHub, Stripe, Wise, Mercury, Blaze billing, Google Docs, Google Drive: each a connection, a sensor and a source of documents |
| People (7) | the three HQ people plus a project lead, a developer, a designer and an operations and finance member |
| Clients (6) | Lanka Print, Ocean Foods, Bluebird Clinics, Kandy Tea, Harbor Logistics, Nila Learning |
| Documents (44) | meetings, Slack and WhatsApp threads, emails, bills, bank and tax notes, grant, deck, policies (105 searchable passages) |
| Policies (6) | client comms, refund, spend, tasks, payments, data; comms, refund and spend have a dated change |
| Skills (6) and agents (5) | client update (A1, A2), transcript to tasks (A3), member progress (A3), spend check (A4), client questions (A5), grant and document draft (A6, A7, A9); one to two workflows in each of the four clusters |
| History | 34 runs, 22 approvals (5 pending), about 140 audit entries, 8 chats, 4 Ask the Brain chats, 6 verified facts, 5 obligations with gaps |

## Gaps, said out loud

| Gap | Why |
|---|---|
| Seeded pending approvals are for viewing | Approve or Reject is refused by the pipeline because no live run holds them. Real ones need scripted signals through S1 |
| No Claude and no Voyage on HQ-2 | Credit is low. Ask the Brain lists the closest passages with sources; vectors are hashed words. Switching on Voyage needs a one-time re-embed (about 105 passages, under USD 0.01) |
| No platform filter or spaces | `Docs/Knowledge_Spaces.md` is still an idea. Platforms show as sensors, connections and document sources only |
| Research shows HQ's results | The Lab runs on port 8000 |
| Connections are records only | Their addresses are placeholders, so nothing polls them and sending into a chat fails with a plain message |
| Needs Docker | The second backend and the seed expect Postgres and SeaweedFS |
