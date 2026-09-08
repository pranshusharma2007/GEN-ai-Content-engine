# OmniFormat AI Engine — Project Overview
**SIH26154 · Team WildCard**

## What This Project Does

OmniFormat AI Engine is a high-performance content transformation system. It ingests ground-truth source material across multiple formats (raw pasted text, PDF documents, Microsoft Word DOCX files, or live web URLs), normalizes and extracts the core textual content, and executes specialized AI agents concurrently to produce 5 leadership-ready, high-value formats:

1. **Strategic Advisory Bulletin**: Structured briefings outlining executive summary, context, strategic implications, risk assessment, and recommended action steps.
2. **Executive Summary**: High-density summaries distilling key objectives, findings, data points, and strategic decisions.
3. **LinkedIn Post**: High-impact thought-leadership posts engineered with punchy hooks, scannable bullet points, actionable takeaways, and relevant hashtags.
4. **X / Twitter Thread**: Sequenced 280-character posts crafted for virality, storytelling, and audience engagement.
5. **Presentation Deck**: Complete slide decks formatted with slide titles, executive bullet points, and speaker notes.

Every generated format undergoes automated **claim-level anti-hallucination verification** against the original normalized source material to ensure factual accuracy and flag any unsupported statements.

The system allows instant copying, direct presentation export to PowerPoint (`.pptx`), direct document export to PDF (`.pdf`), and persists all transformation runs to MongoDB for historical auditing and retrieval.

---

## Architectural Components

### 1. React / Vite / Tailwind Frontend (`gen-ai-content-engine/frontend`)

- **Modern Architecture**: React 19 + Vite + Tailwind CSS v4. A Firebase Auth gate (email/password + Google) fronts the transformation workspace.
- **Source Ingestion Tabs**:
  - Raw Text: Paste plain text or articles.
  - File Upload: Drag-and-drop or browse `.pdf`, `.docx`, and `.txt` files up to 10 MB.
  - Web URL: Input live article URLs with client-side validation.
- **Audience & Tone Controls**: Configure persona, voice, and target recipient.
- **Output Format Matrix**: Multi-select format picker for the 5 specialized formats.
- **Results Workspace**: Side-by-side tabbed viewer showing generated outputs, claim verification badges, individual unsupported claim flags, copy actions, and format-specific download triggers (PPTX / PDF).
- **History Drawer**: Slide-out panel to browse previous transformation runs from MongoDB, inspect metadata, and load full outputs without re-running generation.
- **Aesthetics**: Tailwind CSS v4 design system — dark, professional palette with an indigo accent, hairline-bordered panels, a soft radial backdrop, and calm entrance transitions.

### 2. FastAPI Backend (`gen-ai-content-engine/backend/main.py`)

- **FastAPI Core**: Async REST service running on port `8000`.
- **Source Normalization Pipeline**:
  - `pypdf` for PDF page text extraction.
  - `python-docx` for Word document paragraph and table extraction.
  - `httpx` + `trafilatura` for clean, distraction-free web article extraction with built-in SSRF protection (private/local IP address blocking).
- **Parallel Multi-Agent Generation**:
  - Independent, specialized system and user prompt engineering per format.
  - Orchestrated asynchronously using `asyncio.gather(..., return_exceptions=True)` for fault tolerance and low response latency.
- **Claim-Level Anti-Hallucination Verification Engine**:
  - Evaluates generated statements against the ground-truth normalized source.
  - Flags specific unsupported claims with rationales (shown inline, not removed).
- **Tamper-Evident Integrity Engine**:
  - SHA-256 fingerprint per output at generation time (`hash` / `hash_algo`) plus a combined `run_hash` over the whole run.
  - `POST /verify` (and `GET /verify/{run_id}/{format}`) re-hash content against the recorded fingerprint; the UI surfaces a live pass/fail and an editable "tamper test".
- **Export Endpoints**:
  - `/export/pptx`: Generates formatted multi-slide PowerPoint files using `python-pptx`.
  - `/export/pdf`: Generates clean printable PDF summaries using `reportlab`.
- **Persistence Layer**:
  - Supabase (Postgres) via `supabase-py`, with a local-JSON fallback (`backend/.local_history.json`) when unconfigured.
  - Per-user run history (scoped by Firebase UID): inputs, outputs, ground truth, and verification results.
- **Authentication**:
  - Firebase Authentication. Frontend uses the Firebase Web SDK (email/password + Google). Backend verifies ID tokens with `firebase-admin` when a service account is present, otherwise with `google-auth` against Google's public keys using just `FIREBASE_PROJECT_ID`. Dev-bypass until any Firebase config is set; `AUTH_REQUIRED=true` hard-enforces.
- **Per-Format Multi-Provider Routing**:
  - Each selected format's generation agent runs on its assigned provider (`FORMAT_PROVIDER`, env-overridable via `LLM_FORMAT_*`): LinkedIn / X-thread → Groq; Advisory / Executive Summary / Presentation / Infographic → Gemini. Same source input for all.
  - Shared passes (ground-truth, verify, consistency, diff) task-routed to Gemini via `get_llm_for(task)`.
  - `_RoutedLLM` does automatic cross-provider fallback and records `served_by`; results carry `provider: {assigned, served_by}`. `OllamaAdapter` stub retained for offline/on-prem.
