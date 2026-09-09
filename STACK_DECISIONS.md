# OmniFormat AI Engine — Stack Decisions (locked)

**SIH26154 · Team WildCard** — one line per decision so slides and code stop contradicting each other.

| Area | Decision | Notes |
|---|---|---|
| Frontend framework | **React 19 + Vite** | No Next.js. SPA dashboard, no SSR needed. |
| Styling | **Tailwind CSS v4** (`@tailwindcss/vite`) | Dark, professional design system. Legacy `App.css` kept during incremental migration. |
| Auth | **Firebase Authentication** | Email/password + Google. Frontend Firebase SDK; backend verifies ID tokens with `firebase-admin`. Runs in a dev-bypass mode when unconfigured. |
| Backend | **Python 3.12 + FastAPI** | Async; unchanged. |
| LLM providers | **Multi-provider: Groq + Google Gemini** | **Per-format** generation routing (`FORMAT_PROVIDER`, `LLM_FORMAT_*` env): LinkedIn / X-thread → Groq; Advisory / Exec Summary / Presentation / Infographic → Gemini. Shared analysis passes (ground-truth / verify / consistency / diff) → Gemini. Automatic cross-provider fallback. OpenAI / Anthropic adapters are post-MVP (drop-in — add adapter + set the env value). Ollama stub kept for offline. |
| Data / history store | **Supabase** (Postgres via `supabase-py`) | No MongoDB, no hand-rolled SQLite. Falls back to a local JSON file (`backend/.local_history.json`) when Supabase is unconfigured so History still demos with zero setup. |
| Deployment (target) | Vercel (frontend) + Render/Railway/Fly (backend) | Backend host still to be provisioned. |

## What a judge sees at the repo root
- `gen-ai-content-engine/` — the submission (frontend + backend)
- `STACK_DECISIONS.md`, `OmniFormat_Project_Brief.md`, `PROJECT_OVERVIEW.md`, `OmniFormat AI Engine MVP Plan.pdf` — planning docs
- No stray/unrelated code (`api.py`, `start.py`, `memory-gateway/` referenced in the older MVP plan do not exist in this repo).

## Credentials the team must supply (see `.env.example`)
- `FIREBASE_*` (frontend web config) + `FIREBASE_SERVICE_ACCOUNT_JSON` (backend)
- `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (backend) — run `gen-ai-content-engine/backend/supabase_schema.sql` once in the Supabase SQL editor
- `GROQ_API_KEY` and/or `GEMINI_API_KEY`

## Slide corrections implied by these decisions
- "Gemini" → "Groq + Gemini (task-routed multi-agent)"
- "MongoDB" → "Supabase (Postgres)"
- "Next.js" → "React + Vite"
- Auth slide → "Firebase Authentication"
