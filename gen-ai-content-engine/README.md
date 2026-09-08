# 🚀 OmniFormat AI Engine

**SIH26154 — Gen AI Platform for Automated Content Transformation**  
**Team WildCard**

OmniFormat AI Engine transforms any raw source (pasted text, PDF documents, Word DOCX files, or live web URLs) into 5 high-impact, professional output formats concurrently using specialized multi-agent AI routines, verified with an automated claim-level anti-hallucination verification engine.

---

## 🌟 Key Features

1. **Multi-Source Ingestion & Normalization**:
   - **Pasted Raw Text**: Instant normalization and sanitization.
   - **PDF Documents**: Clean text extraction via `pypdf`.
   - **Word DOCX Files**: Native paragraph and table text extraction via `python-docx`.
   - **Live Web URLs**: High-speed, article-focused extraction with SSRF security safeguards (blocking internal/private IPs) via `httpx` + `trafilatura`.

2. **5 Concurrent Specialized Agents**:
   - 🏛️ **Strategic Advisory Bulletin**: Structured executive briefings with situation, implications, and action plans.
   - 📋 **Executive Summary**: High-density leadership summaries with key takeaways and metrics.
   - 💼 **LinkedIn Post**: High-engagement thought leadership posts with hooks and hashtags.
   - 🧵 **X / Twitter Thread**: Sequenced 280-character threads with strong hooks and CTA.
   - 📊 **Presentation Deck**: Slide-by-slide decks with slide titles, bullet points, and speaker notes.
   - *Executed concurrently via `asyncio.gather` for minimal end-to-end latency.*

3. **Claim-Level Anti-Hallucination Verification**:
   - Cross-checks claims in each generated output against the ground-truth source material.
   - Flags unsupported claims inline (shown, not silently removed).

4. **Tamper-Evident Integrity (SHA-256 hash-logging)**:
   - Every output is fingerprinted with SHA-256 at generation time; the run carries a combined `run_hash`.
   - `POST /verify` re-hashes any content against its recorded fingerprint — the UI shows a live ✓/✗ and a "tamper test" that breaks the hash on any edit.

5. **Export & Download**:
   - Download slide decks as real PowerPoint (`.pptx`) presentations via `python-pptx`.
   - Download executive and advisory documents as clean formatted PDFs via `reportlab`.

6. **Supabase Persistence & History**:
   - Full transformation runs, outputs, verification results, integrity hashes and source metadata saved to Supabase (Postgres), scoped per user; local-JSON fallback when unconfigured.
   - Instant retrieval of past runs from the slide-out history drawer.

7. **Per-Format Multi-Provider Routing**:
   - Each selected output format's agent runs on its **own assigned provider** (same source input for all) — default: LinkedIn & X-thread → **Groq**, Advisory / Executive Summary / Presentation / Infographic → **Gemini**. Override any of them via `LLM_FORMAT_*` env vars.
   - Shared analysis passes (ground-truth, claim verification, consistency, diff) are task-routed to **Gemini**.
   - Automatic cross-provider fallback — if a format's assigned provider fails, the other one serves it and the UI shows "(fallback from …)".
   - `/health` exposes `format_routing`; the frontend tags every format card with its model.
   - **Ollama Adapter (Stub)**: architecture ready for on-prem/local LLM.

8. **Firebase Authentication**: Email/password + Google sign-in on the frontend; the backend verifies Firebase ID tokens — via `firebase-admin` when a service account is set, otherwise via `google-auth` against Google's public keys using only `FIREBASE_PROJECT_ID` — and scopes history per user. Dev-bypass until any Firebase config is supplied.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, Groq SDK, google-genai, firebase-admin, supabase-py, PyPDF, python-docx, Trafilatura, python-pptx, ReportLab.
- **Frontend**: React 19, Vite, Tailwind CSS v4, Firebase Web SDK.
- **Auth**: Firebase Authentication.
- **Database**: Supabase (Postgres) with a local-JSON fallback for zero-setup demos.

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.12
- Node.js 20+ and npm (Vite 8 / Tailwind v4 require Node 20+)
- A Groq and/or Gemini API key
- Optional: a Firebase project (Authentication) and a Supabase project (history)

The app runs with **no credentials** — a dev user is used and history is written to
a local JSON file. Add credentials from `.env.example` to enable real auth + Supabase.

### 2. Configure Environment Variables
Copy `.env.example` in the project root to `.env` and fill in what you have:
```bash
cp .env.example .env
```
Key values: `GROQ_API_KEY` / `GEMINI_API_KEY`, the `VITE_FIREBASE_*` web config +
`FIREBASE_SERVICE_ACCOUNT_JSON`, and `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`
(run `backend/supabase_schema.sql` once in the Supabase SQL editor).

### 3. Start the Backend Server
```bash
cd gen-ai-content-engine/backend

# Create & activate virtual environment (optional but recommended)
python -m venv .venv
# On Windows:
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run FastAPI server
uvicorn main:app --port 8000 --reload
```
The backend will be live at `http://localhost:8000` (API docs at `http://localhost:8000/docs`).

### 4. Start the Frontend Application
In a separate terminal:
```bash
cd gen-ai-content-engine/frontend

# Install dependencies
npm install

# Start Vite dev server
npm run dev
```
Open your browser at `http://localhost:5173`.

---

## 📡 API Endpoints Reference

All endpoints except `/health` accept an `Authorization: Bearer <Firebase ID token>`
header (enforced when `AUTH_REQUIRED=true`; dev-bypass otherwise).

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Service status, available LLM providers, routing, storage backend |
| `POST` | `/transform` | ✓ | Normalize source, run parallel agents, verify claims, SHA-256 hash-log each output, persist run |
| `GET` | `/history` | ✓ | Recent transformation runs for the current user |
| `GET` | `/history/{id}` | ✓ | Full run details with all outputs and verification data |
| `POST` | `/verify` | ✓ | Re-hash `{run_id, format_name, content?}` against the fingerprint recorded at generation → `{verified, stored_hash, computed_hash}` |
| `GET` | `/verify/{id}/{format}` | ✓ | Storage-integrity check — re-hash the stored copy of one output |
| `POST` | `/regenerate` | ✓ | Surgically regenerate selected formats against an updated source |
| `POST` | `/compare_versions` | ✓ | Diff two source versions, list changed facts + affected formats |
| `POST` | `/export/pptx` | ✓ | Generate and download a PowerPoint presentation (.pptx) |
| `POST` | `/export/pdf` | ✓ | Generate and download a formatted PDF document (.pdf) |

---

## 🏛️ Architecture & Data Flow

```
+-------------------------------------------------------------+
|              React + Vite + Tailwind UI                     |
|   Firebase Auth gate → workspace (Text / PDF / DOCX / URL)  |
+------------------------------+------------------------------+
                               | POST /transform  (Bearer ID token)
                               v
+-------------------------------------------------------------+
|   FastAPI  ·  verify Firebase token  ·  Source Normalizer   |
| (SSRF-protected URL fetch, PyPDF, python-docx, sanitization)|
+------------------------------+------------------------------+
                               | Normalized source
                               v
+-------------------------------------------------------------+
|   Ground-truth extraction (Gemini)                          |
|   Concurrent Multi-Agent Engine (Groq) — asyncio.gather     |
|   Claim verification + cross-format consistency (Gemini)    |
+------------------------------+------------------------------+
                               |
            +------------------+------------------+
            |                                     |
            v                                     v
+-----------------------+             +-----------------------+
|  Supabase (Postgres)  |             |  Side-by-Side Results |
|  per-user run history |             |  (Copy / PPTX / PDF)  |
+-----------------------+             +-----------------------+
```

---

## 👥 Team WildCard
Smart India Hackathon (SIH26154)
