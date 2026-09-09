# OmniFormat AI Engine — Team Brief
**SIH26154 | Gen AI Platform for Automated Content Transformation | Team WildCard**

---

## The problem, in one line
Organizations spend hours manually rewriting the same source content (reports, advisories, articles) into different formats — LinkedIn posts, tweets, executive summaries, official advisories, slide decks — each requiring different tone, structure, and expertise.

## Our solution, in one line
One dashboard. Paste or upload a source document. Pick which output formats you want. Get all of them generated in parallel, in seconds — grounded in the source, not hallucinated.

---

## How it actually works (the full flow)

1. **Input** — Operator pastes text, uploads a PDF/DOCX, or pastes a URL
2. **Parsing** — Backend extracts and normalizes the content into clean text
3. **Format selection** — Operator picks output types (Advisory, Executive Summary, LinkedIn Post, Twitter Thread, Presentation) and sets tone/audience
4. **Parallel generation** — Instead of one big AI prompt trying to do everything, we run **separate, specialized prompts per format** — a "LinkedIn agent," a "Twitter agent," an "Advisory agent," etc. — all firing **at the same time** (not one after another), all reading the same source
5. **Source-grounding check** — Every generated claim gets checked against the original document. If something can't be traced back to the source, it gets flagged instead of silently shown as fact
6. **Output** — All formats appear side-by-side, ready to copy or export as real .pptx/.pdf files

## Why separate agents per format (not one AI doing everything)

- **Focus reduces mistakes** — an AI prompt with one narrow job ("just write a 280-character tweet from this") makes fewer errors than one prompt juggling five different format rules at once
- **One failure doesn't break everything** — if the Twitter output breaks, the Advisory and Summary outputs still work fine, because they're independent
- **Genuinely fast** — since they all run in parallel, generating 5 formats takes about the same time as generating 1
- **Matches what we're pitching** — we're calling this a "multi-agent" system, so this is us actually building it that way, not just using the term as a buzzword

## Why this isn't "just ChatGPT with extra steps" (the answer if a judge asks)

- The operator needs **zero prompt-writing skill** — they click checkboxes, we've already engineered the prompts behind the scenes
- **One click generates all formats at once**, instead of five separate back-and-forth conversations
- **Consistency** — every advisory looks like an advisory, every summary follows the same structure, no matter who's using it
- **Data stays internal** — sensitive government content doesn't get pasted into a public chatbot; for classified use, we can run entirely on a secure, offline model instead of the cloud
- **Source-grounding** — every fact is traceable back to the original document, which most raw chatbot use doesn't offer

## Our tech stack (why we picked each piece)

| Layer | Tech | Why |
|---|---|---|
| Frontend | Next.js (React), Tailwind CSS | Fast, responsive dashboard |
| Backend | FastAPI (Python) | Built for async — perfect for running multiple AI calls at once |
| AI Engine | Google Gemini API | Fast, reliable, handles multiple languages |
| Secure AI (roadmap) | Ollama (Llama 3/Mistral) | Can run fully offline for classified data — no internet needed |
| Document parsing | PyPDF2 / python-docx | Pulls clean text out of PDFs and Word docs |
| Database | MongoDB | Stores source content, generated outputs, and history |
| Deployment | Vercel (frontend), Render/AWS (backend) | Scales without heavy ops work |

## What actually makes us stand out (in priority order)

1. **The source-grounding/anti-hallucination check** — most hackathon AI tools don't handle this at all. We can *show* a claim getting flagged live, which proves it's real, not just a slide claim.
2. **The security story** — dual-mode LLM (cloud for speed, offline model for classified data) directly answers a real concern that a government org like NTRO would actually have.
3. **The live demo moment** — paste one real article on stage, generate 4-5 formats in under 15 seconds, side by side. That's the moment judges remember.

The multi-agent architecture is *how* we build it properly — it's not the pitch itself. Lead with points 1–3 above when presenting; the architecture is the engineering that makes those points true.

## What we're explicitly NOT building for the hackathon MVP (say this if asked, don't fake it)
- Real video generation (we generate the script/storyboard, not an actual video)
- Actual infographic images (we generate the content/layout plan, not a rendered graphic)
- Full production-grade Ollama deployment (architected for it, running on Gemini for the demo)
- Image/video as input formats (text, PDF, DOCX, URL only for MVP)

---

## One-sentence summary to remember
**"Paste one document, pick your formats, get a full communications package in seconds — every claim traceable back to the source, and built to run securely even without internet access."**
