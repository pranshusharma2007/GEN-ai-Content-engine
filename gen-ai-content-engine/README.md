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
   - Evaluates factual alignment, computes confidence scores, and flags unsupported claims.

4. **Export & Download**:
   - Download slide decks as real PowerPoint (`.pptx`) presentations via `python-pptx`.
   - Download executive and advisory documents as clean formatted PDFs via `reportlab`.

5. **MongoDB Persistence & History**:
   - Full transformation runs, generated outputs, verification reports, and source metadata saved to MongoDB.
   - Instant retrieval of past transformation runs from the slide-out history drawer.

6. **LLM Provider Abstraction**:
   - **Groq Adapter**: Ultra-fast inference with `llama-3.3-70b-versatile` (primary) and `llama3-8b-8192` (fallback).
   - **Ollama Adapter (Stub)**: Provider-swappable architecture ready for on-premise/local LLM deployment.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, Pydantic, Groq SDK, PyMongo, PyPDF, python-docx, Trafilatura, python-pptx, ReportLab.
- **Frontend**: React 18, Vite, Vanilla CSS design system, Lucide-inspired SVG icons.
- **Database**: MongoDB (Atlas or local).

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ and npm
- Groq API Key ([Get one free at console.groq.com](https://console.groq.com/))
- MongoDB URI (Atlas free tier or local MongoDB instance)

### 2. Configure Environment Variables
Copy `.env.example` in the project root to `.env`:
```bash
cp .env.example .env
```
Update `.env` with your credentials:
```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_groq_api_key_here
MONGODB_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=omniformat_ai
FRONTEND_ORIGINS=http://localhost:5173,http://localhost:3000
VITE_GEN_AI_API_URL=http://localhost:8000
```

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

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service status, LLM provider, and DB connectivity |
| `POST` | `/transform` | Normalize source, run parallel agents, verify claims, persist run |
| `GET` | `/history` | Fetch recent transformation runs (id, timestamp, source type, formats) |
| `GET` | `/history/{id}` | Retrieve full run details with all outputs and verification data |
| `POST` | `/export/pptx` | Generate and download PowerPoint presentation (.pptx) |
| `POST` | `/export/pdf` | Generate and download formatted PDF document (.pdf) |

---

## 🏛️ Architecture & Data Flow

```
+-------------------------------------------------------------+
|                      React / Vite UI                        |
|   (Pasted Text / PDF / DOCX / URL + Format/Tone Selection)  |
+------------------------------+------------------------------+
                               | POST /transform
                               v
+-------------------------------------------------------------+
|                 FastAPI Source Normalizer                   |
| (SSRF-protected URL fetch, PyPDF, python-docx, sanitization)|
+------------------------------+------------------------------+
                               | Normalized ground truth text
                               v
+-------------------------------------------------------------+
|               Concurrent Multi-Agent Engine                 |
|   (Advisory, Executive, LinkedIn, X Thread, Presentation)   |
|               asyncio.gather(agent_1 ... agent_5)           |
+------------------------------+------------------------------+
                               | Generated outputs
                               v
+-------------------------------------------------------------+
|             Anti-Hallucination Verification                 |
|        (Claim extraction & verification against source)     |
+------------------------------+------------------------------+
                               |
            +------------------+------------------+
            |                                     |
            v                                     v
+-----------------------+             +-----------------------+
|  MongoDB Persistence  |             |  Side-by-Side Results |
| (History & Audit Log) |             |  (Copy / PPTX / PDF)  |
+-----------------------+             +-----------------------+
```

---

## 👥 Team WildCard
Smart India Hackathon (SIH26154)
