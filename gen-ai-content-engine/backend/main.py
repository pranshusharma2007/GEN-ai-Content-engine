"""
OmniFormat AI Engine — Backend
SIH26154 · Team WildCard

Architecture:
  source → normalize_source() → 5 parallel agents → verify_claims() → MongoDB → response
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import os
import re
import textwrap
import uuid
import zipfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

# ── Load environment ─────────────────────────────────────────────────────────
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)
load_dotenv()  # local fallback

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

# ── Configuration ─────────────────────────────────────────────────────────────
FRONTEND_ORIGINS = [
    x.strip()
    for x in os.environ.get(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    if x.strip()
]

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "omniformat_ai")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_SOURCE_CHARS = 120_000

SUPPORTED_TONES = {
    "Professional",
    "Authoritative & Strategic",
    "Casual & Engaging",
    "Urgent & Action-Oriented",
    "Inspirational",
}
SUPPORTED_AUDIENCES = {
    "Leadership / Execs",
    "General Public",
    "Tech / Developers",
    "Sales / Marketing",
    "Stakeholders & Investors",
}
SUPPORTED_FORMATS = {
    "advisory",
    "executive_summary",
    "linkedin",
    "x_thread",
    "presentation",
}

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="OmniFormat AI Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# LLM Provider Abstraction
# ═══════════════════════════════════════════════════════════════════════════════

class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        """Synchronous chat completion. Returns response text."""


class GroqAdapter(LLMProvider):
    """Groq-hosted LLM adapter with intelligent model discovery and fallback."""

    CANDIDATE_MODELS = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile",
        "llama3-8b-8192",
        "qwen/qwen3.8-27b",
        "qwen/qwen3.6-27b",
    ]

    def __init__(self, api_key: str) -> None:
        from groq import Groq
        self._client = Groq(api_key=api_key, timeout=60.0, max_retries=2)
        self._models: list[str] = []
        try:
            available = {m.id for m in self._client.models.list().data}
            self._models = [m for m in self.CANDIDATE_MODELS if m in available]
            if not self._models:
                self._models = [
                    m for m in available
                    if not any(x in m for x in ("whisper", "guard", "audio"))
                ]
            print(f"[GroqAdapter] Active models in priority order: {self._models}")
        except Exception as exc:
            print(f"[GroqAdapter] Model discovery failed ({exc}), using static candidates")
            self._models = list(self.CANDIDATE_MODELS)

    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        last_err = None
        for model in self._models:
            try:
                resp = self._client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    model=model,
                    temperature=temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:
                print(f"[GroqAdapter] model={model} failed: {exc}")
                last_err = exc
        raise RuntimeError(f"All Groq models failed. Last error: {last_err}")


class OllamaAdapter(LLMProvider):
    """Stub Ollama adapter — demonstrates provider-switching architecture.
    Deploy Ollama locally and set LLM_PROVIDER=ollama to activate.
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url

    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        raise NotImplementedError(
            "OllamaAdapter is a stub. Deploy Ollama locally and implement this adapter."
        )


def _build_provider() -> LLMProvider:
    provider = LLM_PROVIDER.lower()
    if provider == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        return GroqAdapter(api_key=GROQ_API_KEY)
    if provider == "ollama":
        return OllamaAdapter()
    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider!r}")


_llm: Optional[LLMProvider] = None


def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = _build_provider()
    return _llm


# ═══════════════════════════════════════════════════════════════════════════════
# MongoDB Client
# ═══════════════════════════════════════════════════════════════════════════════

_mongo_collection = None


def _get_collection():
    global _mongo_collection
    if _mongo_collection is not None:
        return _mongo_collection
    if not MONGODB_URI:
        print("[MongoDB] MONGODB_URI not set — history persistence disabled.")
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGODB_DATABASE]
        _mongo_collection = db["transformations"]
        print("[MongoDB] Connected successfully.")
        return _mongo_collection
    except Exception as exc:
        print(f"[MongoDB] Connection failed: {exc}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Source Normalization Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def _normalize_text(raw: str) -> str:
    """Clean and trim a text string."""
    text = raw.strip()
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_SOURCE_CHARS]


def _extract_pdf(content: bytes) -> str:
    import pypdf
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return _normalize_text("\n".join(filter(None, pages)))
    except Exception as exc:
        raise ValueError(f"PDF could not be read: {exc}") from exc


def _extract_docx(content: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise ValueError("DOCX support unavailable — install python-docx.") from exc
    try:
        doc = Document(io.BytesIO(content))
        parts: list[str] = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text.strip())
        # Also extract table text
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    parts.append(row_text)
        if not parts:
            raise ValueError("DOCX file appears to contain no readable text.")
        return _normalize_text("\n\n".join(parts))
    except (KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ValueError(f"DOCX could not be read: {exc}") from exc


def _extract_url(url: str) -> str:
    """Fetch and extract article text from a URL using httpx + trafilatura."""
    import httpx
    import trafilatura

    # Block private/local network URLs
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are supported.")

    hostname = parsed.hostname or ""
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError("Access to private/local network URLs is not allowed.")
    except ValueError as exc:
        if "private" in str(exc) or "local" in str(exc):
            raise
        # Not an IP address — hostname is fine
    if hostname in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Access to localhost is not allowed.")

    try:
        response = httpx.get(
            url,
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "OmniFormat-AI-Engine/2.0"},
        )
        response.raise_for_status()
    except httpx.TimeoutException:
        raise ValueError("The URL timed out. Please try again or paste the text directly.")
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"URL returned HTTP {exc.response.status_code}.") from exc
    except Exception as exc:
        raise ValueError(f"Could not fetch URL: {exc}") from exc

    extracted = trafilatura.extract(
        response.text,
        include_tables=True,
        include_comments=False,
        no_fallback=False,
    )
    if not extracted or len(extracted.strip()) < 100:
        raise ValueError(
            "Could not extract readable article content from this URL. "
            "Try pasting the text directly."
        )
    return _normalize_text(extracted)


def normalize_source(
    text: str = "",
    file_content: Optional[bytes] = None,
    filename: str = "",
    url: str = "",
) -> tuple[str, str]:
    """
    Returns (normalized_text, source_type).
    source_type: 'text' | 'pdf' | 'docx' | 'url'
    """
    if url:
        return _extract_url(url), "url"

    if file_content is not None and filename:
        fname = filename.lower()
        if fname.endswith(".pdf"):
            return _extract_pdf(file_content), "pdf"
        if fname.endswith(".docx"):
            return _extract_docx(file_content), "docx"
        if fname.endswith((".txt", ".md")):
            decoded = file_content.decode("utf-8", errors="ignore")
            normalized = _normalize_text(decoded)
            if not normalized:
                raise ValueError("The text file appears to be empty.")
            return normalized, "text"
        raise ValueError(
            f"Unsupported file type: {filename!r}. "
            "Accepted: .pdf, .docx, .txt"
        )

    if text:
        normalized = _normalize_text(text)
        if not normalized:
            raise ValueError("Source text is empty after normalization.")
        return normalized, "text"

    raise ValueError("No source provided. Paste text, upload a file, or enter a URL.")


# ═══════════════════════════════════════════════════════════════════════════════
# Specialized Generation Agents
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_json_block(raw: str) -> dict:
    """Robustly parse JSON from model output, tolerating markdown fences."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            return json.loads(match.group(1))
        raise


def _strip_emojis(text: str) -> str:
    pattern = re.compile(
        r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d\u20e3]"
    )
    return pattern.sub("", text)


def generate_advisory(source: str, tone: str, audience: str, llm: LLMProvider) -> dict:
    system = textwrap.dedent(f"""
        You are a Senior Strategic Advisor producing a formal advisory bulletin.
        Tone: {tone}. Target Audience: {audience}.

        Structure your advisory with these exact sections:
        1. EXECUTIVE SUMMARY (2–3 sentences)
        2. SITUATION OVERVIEW
        3. THREAT / OPPORTUNITY ASSESSMENT
        4. STRATEGIC IMPERATIVES (numbered list)
        5. GOVERNANCE & IMPLEMENTATION GUIDANCE
        6. RECOMMENDED ACTIONS (step-by-step roadmap)
        7. CONCLUSION

        Rules:
        - Professional, formal register. No emojis.
        - Output plain text (no markdown bold/italics).
        - STRICT GROUNDING: Use only facts from the supplied source. NEVER invent or fabricate facts, metrics, organizations, or events.
        - INSUFFICIENT OR VAGUE SOURCE: If the source lacks sufficient factual substance or background for a formal strategic advisory:
          * NEVER invent fictional companies, case studies, or scenarios.
          * Provide a structured advisory template with explicit bracketed placeholders (e.g., [Organization/Company], [Specific Threat/Opportunity], [Key Metric], [Recommended Action]) or return "Insufficient source information: Please provide contextual background and data to generate a strategic advisory."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the advisory now:"
    content = llm.chat(system, user, temperature=0.4)
    return {"content": _strip_emojis(content)}


def generate_executive_summary(source: str, tone: str, audience: str, llm: LLMProvider) -> dict:
    system = textwrap.dedent(f"""
        You are an Executive Communications Specialist producing a concise executive summary.
        Tone: {tone}. Target Audience: {audience}.

        Structure:
        1. CONTEXT & BACKGROUND (1–2 sentences)
        2. KEY FINDINGS (3–5 bullet points)
        3. STRATEGIC IMPLICATIONS
        4. RISK CONSIDERATIONS
        5. RECOMMENDED ACTIONS (4–6 concrete actions)

        Rules:
        - Executives have 3 minutes to read this. Be dense and precise.
        - No emojis, no filler phrases.
        - Output plain text.
        - STRICT GROUNDING: Use only facts from the source. NEVER fabricate metrics, initiatives, or company names.
        - INSUFFICIENT OR VAGUE SOURCE: If the source contains insufficient factual data to summarize:
          * NEVER invent fictional achievements or operational details.
          * Provide a structured executive summary template using bracketed placeholders (e.g., [Initiative/Project], [Key Finding], [Metric/KPI], [Action Owner]) or return "Insufficient source information: Please provide detailed report content or data to summarize."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the executive summary now:"
    content = llm.chat(system, user, temperature=0.3)
    return {"content": _strip_emojis(content)}


def generate_linkedin(source: str, tone: str, audience: str, llm: LLMProvider) -> dict:
    system = textwrap.dedent(f"""
        You are a LinkedIn content strategist writing a high-engagement professional post.
        Tone: {tone}. Target Audience: {audience}.

        Structure:
        - HOOK LINE (first sentence — grabs attention, stands alone)
        - [blank line]
        - 2–3 lines of context or story
        - [blank line]
        - 3–5 key insights as short bullet points (use "—" as bullet)
        - [blank line]
        - Key takeaway or lesson (1–2 sentences)
        - [blank line]
        - Thought-provoking closing question (1 sentence)
        - [blank line]
        - 3–5 relevant hashtags

        Rules:
        - NEVER use emojis.
        - 150–250 words total.
        - Conversational but professional.
        - STRICT GROUNDING: NEVER invent factual details that are absent from the source. Do NOT invent company names (e.g., "XYZ Corporation"), job titles, career achievements, or personal background.
        - INSUFFICIENT OR VAGUE SOURCE: If the source is brief, vague, or a prompt/request (such as "give company joining post" or "announcement"):
          * NEVER invent fictional details to fill the gaps.
          * Return a useful generic template using clear bracketed placeholders (e.g., [Company Name], [Role], [Name], [Key Responsibility], [Previous Experience], [Key Goal/Achievement]).
          * Alternatively, return a clear "Insufficient source information" response explaining what details are needed.
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the LinkedIn post now:"
    content = llm.chat(system, user, temperature=0.5)
    return {"content": _strip_emojis(content)}


def generate_x_thread(source: str, tone: str, audience: str, llm: LLMProvider) -> dict:
    system = textwrap.dedent(f"""
        You are a social media strategist writing an X/Twitter thread.
        Tone: {tone}. Target Audience: {audience}.

        Structure:
        Tweet 1/N: Hook — bold opening statement. Max 280 chars.
        Tweet 2/N: Context / background.
        Tweet 3/N–6/N: One key point per tweet. Start each with the number (e.g. "3/7").
        Final tweet: Recap + call to action. End with relevant hashtags.

        Rules:
        - Generate 5–8 tweets total.
        - Each tweet ≤ 280 characters.
        - No emojis.
        - Number each tweet (1/N format).
        - Separate tweets with a blank line.
        - STRICT GROUNDING: Only facts from the source. NEVER invent fictional organizations, statistics, or stories.
        - INSUFFICIENT OR VAGUE SOURCE: If the source lacks sufficient detail:
          * Do NOT invent fictional facts.
          * Return a thread template with bracketed placeholders (e.g., [Topic/Announcement], [Key Stat], [Takeaway]) or return "Insufficient source information: Please provide source material to build an X thread."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the X/Twitter thread now:"
    content = llm.chat(system, user, temperature=0.5)
    return {"content": _strip_emojis(content)}


def generate_presentation(source: str, tone: str, audience: str, llm: LLMProvider) -> dict:
    system = textwrap.dedent(f"""
        You are a presentation designer creating a structured slide deck outline.
        Tone: {tone}. Target Audience: {audience}.

        For each slide output:
        SLIDE [N]: [Title]
        BULLETS:
        — [bullet 1]
        — [bullet 2]
        — [bullet 3]
        SPEAKER NOTES: [2–3 sentences the presenter should say]

        Requirements:
        - Slide 1: Title slide with presentation title and subtitle
        - Slides 2–7: Content slides (key points, findings, analysis)
        - Final slide: Conclusion / Key Takeaways / Next Steps

        Rules:
        - 7–10 slides total.
        - 3–5 bullets per content slide.
        - No emojis. Plain text only.
        - STRICT GROUNDING: Only facts from the source. NEVER fabricate statistics, company names, or case studies.
        - INSUFFICIENT OR VAGUE SOURCE: If the source lacks detail:
          * Do NOT invent fictional entities or data.
          * Provide a slide deck outline template using clear bracketed placeholders (e.g., [Company/Topic], [Key Finding], [Metric]) or return "Insufficient source information: Please provide topic details or presentation content."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the presentation outline now:"
    content = llm.chat(system, user, temperature=0.4)
    return {"content": _strip_emojis(content), "_raw_outline": content}


# ═══════════════════════════════════════════════════════════════════════════════
# Claim-Level Verification
# ═══════════════════════════════════════════════════════════════════════════════

_VERIFIER_SYSTEM = textwrap.dedent("""
    You are a fact-checking assistant performing source-grounding verification.
    Your job is to identify individual factual claims in the generated output
    and determine whether each claim is supported by the source text.

    Output ONLY a valid JSON object with this exact structure:
    {
      "claims": [
        {
          "claim": "the specific claim text",
          "status": "supported",
          "evidence": "the exact or paraphrased supporting text from source"
        },
        {
          "claim": "the specific claim text",
          "status": "unsupported",
          "evidence": null,
          "reason": "No supporting information found in source"
        }
      ],
      "unsupported_count": 0
    }

    Rules:
    - Extract 3–8 specific factual claims from the generated output.
    - Only check facts, statistics, named entities, and specific assertions.
    - Do NOT check opinions, recommendations, or stylistic content.
    - If a claim is a general recommendation derived from facts, mark as "supported".
    - Placeholders in square brackets (e.g. [Company Name], [Role], [Name]) and generic template variables are NOT factual claims; do NOT mark placeholders as unsupported claims.
    - If the output contains specific factual entities or claims (e.g. specific company names like "XYZ Corporation", job titles, specific numbers) that do not appear in the source, mark them as "unsupported".
    - If the output is a generic template with placeholders or states "Insufficient source information", return {"claims": [], "unsupported_count": 0}.
    - unsupported_count must equal the number of claims with status "unsupported".
    - Do NOT rewrite or remove unsupported claims from the original — just flag them.
    - Output raw JSON only — no markdown fences, no explanation.
""").strip()


def verify_claims(source: str, generated: str, llm: LLMProvider) -> dict:
    """Run a verification pass on one generated output against the source."""
    user = f"SOURCE:\n{source[:8000]}\n\nGENERATED OUTPUT:\n{generated[:4000]}\n\nVerify claims now:"
    try:
        raw = llm.chat(_VERIFIER_SYSTEM, user, temperature=0.1)
        result = _extract_json_block(raw)
        # Validate structure
        if "claims" not in result:
            raise ValueError("Missing 'claims' key")
        unsupported = sum(
            1 for c in result["claims"] if c.get("status") == "unsupported"
        )
        result["unsupported_count"] = unsupported
        return result
    except Exception as exc:
        print(f"[Verifier] Failed: {exc}")
        return {
            "claims": [],
            "unsupported_count": 0,
            "error": "Verification could not be completed.",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Runner (Concurrent)
# ═══════════════════════════════════════════════════════════════════════════════

FORMAT_FN_MAP = {
    "advisory": generate_advisory,
    "executive_summary": generate_executive_summary,
    "linkedin": generate_linkedin,
    "x_thread": generate_x_thread,
    "presentation": generate_presentation,
}


async def _run_agent(
    fmt: str,
    source: str,
    tone: str,
    audience: str,
    llm: LLMProvider,
) -> tuple[str, dict]:
    """Run one generation agent + verification. Returns (format, result_dict)."""
    fn = FORMAT_FN_MAP[fmt]
    try:
        gen_result = await run_in_threadpool(fn, source, tone, audience, llm)
        content = gen_result.get("content", "")
        # Verify generated content against source
        verification = await run_in_threadpool(verify_claims, source, content, llm)
        return fmt, {
            "status": "success",
            "content": content,
            "verification": verification,
        }
    except Exception as exc:
        print(f"[Agent:{fmt}] Failed: {exc}")
        return fmt, {
            "status": "error",
            "error": str(exc),
            "content": None,
            "verification": None,
        }


async def run_agents_concurrently(
    formats: list[str],
    source: str,
    tone: str,
    audience: str,
    llm: LLMProvider,
) -> dict:
    """Run all selected format agents concurrently. One failure ≠ all fail."""
    tasks = [
        _run_agent(fmt, source, tone, audience, llm)
        for fmt in formats
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return dict(results)


# ═══════════════════════════════════════════════════════════════════════════════
# MongoDB Persistence
# ═══════════════════════════════════════════════════════════════════════════════

def _save_to_mongo(document: dict) -> None:
    col = _get_collection()
    if col is None:
        return
    try:
        col.insert_one(document)
    except Exception as exc:
        print(f"[MongoDB] Save failed: {exc}")


def _fetch_history(limit: int = 50) -> list[dict]:
    col = _get_collection()
    if col is None:
        return []
    try:
        cursor = col.find(
            {},
            {
                "_id": 0,
                "run_id": 1,
                "source.type": 1,
                "source.preview": 1,
                "parameters": 1,
                "created_at": 1,
            },
        ).sort("created_at", -1).limit(limit)
        return list(cursor)
    except Exception as exc:
        print(f"[MongoDB] History fetch failed: {exc}")
        return []


def _fetch_run(run_id: str) -> Optional[dict]:
    col = _get_collection()
    if col is None:
        return None
    try:
        doc = col.find_one({"run_id": run_id}, {"_id": 0})
        return doc
    except Exception as exc:
        print(f"[MongoDB] Fetch run failed: {exc}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Startup check
# ═══════════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    if not GROQ_API_KEY and LLM_PROVIDER == "groq":
        print("[WARN] GROQ_API_KEY not set. Generation will fail.")
    if not MONGODB_URI:
        print("[WARN] MONGODB_URI not set. History persistence disabled.")
    else:
        await run_in_threadpool(_get_collection)
    print("[OmniFormat] Backend started.")


# ═══════════════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
@app.get("/health")
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "OmniFormat AI Engine",
        "version": "2.0.0",
        "llm_provider": LLM_PROVIDER,
        "database": "connected" if MONGODB_URI else "disabled",
    }


@app.post("/transform")
@app.post("/api/transform")
async def transform_content(
    request: Request,
    file: Optional[UploadFile] = None,
    text: Optional[str] = Form(""),
    url: Optional[str] = Form(""),
    formats: Optional[str] = Form("[]"),
    tone: Optional[str] = Form("Professional"),
    audience: Optional[str] = Form("Leadership / Execs"),
):
    # ── Validate formats ──────────────────────────────────────────────────
    try:
        fmt_list: list[str] = json.loads(formats or "[]")
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="formats must be valid JSON array.")
    if not isinstance(fmt_list, list) or not fmt_list:
        raise HTTPException(status_code=400, detail="Select at least one output format.")
    invalid = [f for f in fmt_list if f not in SUPPORTED_FORMATS]
    if invalid:
        raise HTTPException(
            status_code=400, detail=f"Unsupported format(s): {invalid}"
        )

    # ── Validate tone/audience ────────────────────────────────────────────
    tone = (tone or "Professional").strip()
    if tone not in SUPPORTED_TONES:
        raise HTTPException(status_code=400, detail="Unsupported tone.")
    audience = (audience or "Leadership / Execs").strip()
    if audience not in SUPPORTED_AUDIENCES:
        raise HTTPException(status_code=400, detail="Unsupported audience.")

    # ── Read file ─────────────────────────────────────────────────────────
    file_content: Optional[bytes] = None
    filename: str = ""
    if file and file.filename:
        file_content = await file.read()
        if len(file_content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="File exceeds 10 MB limit.")
        filename = file.filename.lower()

    # ── Normalize source (CPU-bound — run in threadpool) ──────────────────
    clean_url = (url or "").strip()
    clean_text = (text or "").strip()
    try:
        normalized_source, source_type = await run_in_threadpool(
            normalize_source,
            clean_text,
            file_content,
            filename,
            clean_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── Get LLM provider ──────────────────────────────────────────────────
    try:
        llm = get_llm()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # ── Run agents concurrently ───────────────────────────────────────────
    results = await run_agents_concurrently(
        formats=fmt_list,
        source=normalized_source,
        tone=tone,
        audience=audience,
        llm=llm,
    )

    # ── Persist to MongoDB ────────────────────────────────────────────────
    run_id = str(uuid.uuid4())
    preview = normalized_source[:300] + "..." if len(normalized_source) > 300 else normalized_source
    document = {
        "run_id": run_id,
        "source": {
            "type": source_type,
            "content": normalized_source[:50000],  # cap stored content
            "preview": preview,
            "url": clean_url if source_type == "url" else None,
        },
        "parameters": {
            "formats": fmt_list,
            "tone": tone,
            "audience": audience,
        },
        "results": results,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await run_in_threadpool(_save_to_mongo, document)

    return {
        "run_id": run_id,
        "source": {
            "type": source_type,
            "preview": preview,
        },
        "results": results,
    }


@app.get("/history")
@app.get("/api/history")
async def get_history():
    entries = await run_in_threadpool(_fetch_history)
    return {"history": entries}


@app.get("/history/{run_id}")
@app.get("/api/history/{run_id}")
async def get_history_item(run_id: str):
    doc = await run_in_threadpool(_fetch_run, run_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found.")
    return doc


# ── PPTX Export ───────────────────────────────────────────────────────────────

def _build_pptx(outline: str, title: str = "Presentation") -> bytes:
    """Parse presentation outline and generate a real .pptx file."""
    from pptx import Presentation as PptxPresentation
    from pptx.util import Inches, Pt

    prs = PptxPresentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    slide_layout_title = prs.slide_layouts[0]  # title slide
    slide_layout_content = prs.slide_layouts[1]  # title + content

    # Parse slides from outline
    slide_blocks = re.split(r"(?=SLIDE\s+\d+:)", outline.strip())
    slide_blocks = [b.strip() for b in slide_blocks if b.strip()]

    slides_data = []
    for block in slide_blocks:
        lines = block.split("\n")
        slide_title = ""
        bullets = []
        speaker_notes = ""
        in_bullets = False
        in_notes = False

        for line in lines:
            line = line.strip()
            if re.match(r"SLIDE\s+\d+:", line):
                slide_title = re.sub(r"SLIDE\s+\d+:\s*", "", line).strip()
                in_bullets = False
                in_notes = False
            elif line.upper().startswith("BULLETS:") or line.upper().startswith("KEY POINTS:"):
                in_bullets = True
                in_notes = False
            elif line.upper().startswith("SPEAKER NOTES:"):
                in_notes = True
                in_bullets = False
                notes_text = re.sub(r"SPEAKER NOTES:\s*", "", line, flags=re.IGNORECASE).strip()
                if notes_text:
                    speaker_notes += notes_text + " "
            elif in_notes:
                speaker_notes += line + " "
            elif in_bullets and (line.startswith("—") or line.startswith("-") or line.startswith("•")):
                bullet_text = re.sub(r"^[—\-•]\s*", "", line).strip()
                if bullet_text:
                    bullets.append(bullet_text)
            elif in_bullets and line:
                bullets.append(line)

        if slide_title:
            slides_data.append({
                "title": slide_title,
                "bullets": bullets,
                "notes": speaker_notes.strip(),
            })

    # If parsing failed, create one slide from raw text
    if not slides_data:
        slides_data = [{"title": title, "bullets": [outline[:500]], "notes": ""}]

    for i, slide_data in enumerate(slides_data):
        if i == 0:
            slide = prs.slides.add_slide(slide_layout_title)
            tf_title = slide.shapes.title
            tf_sub = slide.placeholders[1]
            tf_title.text = slide_data["title"]
            tf_sub.text = f"Generated by OmniFormat AI Engine"
        else:
            slide = prs.slides.add_slide(slide_layout_content)
            tf_title = slide.shapes.title
            tf_title.text = slide_data["title"]
            if slide.placeholders[1] and slide_data["bullets"]:
                tf = slide.placeholders[1].text_frame
                tf.clear()
                for j, bullet in enumerate(slide_data["bullets"]):
                    if j == 0:
                        tf.paragraphs[0].text = bullet
                        tf.paragraphs[0].level = 0
                    else:
                        p = tf.add_paragraph()
                        p.text = bullet
                        p.level = 0

        # Add speaker notes
        if slide_data["notes"]:
            notes_slide = slide.notes_slide
            notes_tf = notes_slide.notes_text_frame
            notes_tf.text = slide_data["notes"]

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()


def _build_pdf(content: str, format_name: str) -> bytes:
    """Generate a proper PDF from text content using ReportLab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        HRFlowable,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "OmniTitle",
        parent=styles["Title"],
        fontSize=20,
        textColor=colors.HexColor("#1A1A2E"),
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    heading_style = ParagraphStyle(
        "OmniHeading",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=colors.HexColor("#2C3E50"),
        spaceBefore=14,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "OmniBody",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#2C3E50"),
        leading=16,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "OmniMeta",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#7F8C8D"),
        spaceAfter=16,
    )

    story = []

    # Header
    story.append(Paragraph(format_name, title_style))
    story.append(
        Paragraph(
            f"Generated by OmniFormat AI Engine · {datetime.now().strftime('%B %d, %Y')}",
            meta_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7")))
    story.append(Spacer(1, 0.3 * cm))

    # Parse and render content
    lines = content.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 0.2 * cm))
            continue

        # Detect section headings (ALL CAPS or numbered sections)
        is_heading = (
            stripped.isupper()
            or re.match(r"^\d+\.\s+[A-Z]", stripped)
            or re.match(r"^[A-Z][A-Z &/]+:", stripped)
        )

        if is_heading:
            story.append(Paragraph(stripped, heading_style))
        elif stripped.startswith(("—", "-", "•")):
            bullet_text = re.sub(r"^[—\-•]\s*", "• ", stripped)
            story.append(Paragraph(bullet_text, body_style))
        else:
            # Escape special XML chars for ReportLab
            safe = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, body_style))

    doc.build(story)
    buf.seek(0)
    return buf.read()


@app.post("/export/pptx")
@app.post("/api/export/pptx")
async def export_pptx(request: Request):
    body = await request.json()
    content = body.get("content", "")
    run_title = body.get("title", "Presentation")
    if not content:
        raise HTTPException(status_code=400, detail="No content provided.")
    try:
        pptx_bytes = await run_in_threadpool(_build_pptx, content, run_title)
    except Exception as exc:
        print(f"[PPTX] Build failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to generate PPTX file.")
    return StreamingResponse(
        io.BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f'attachment; filename="omniformat-presentation.pptx"'
        },
    )


@app.post("/export/pdf")
@app.post("/api/export/pdf")
async def export_pdf(request: Request):
    body = await request.json()
    content = body.get("content", "")
    format_name = body.get("format_name", "Document")
    if not content:
        raise HTTPException(status_code=400, detail="No content provided.")
    try:
        pdf_bytes = await run_in_threadpool(_build_pdf, content, format_name)
    except Exception as exc:
        print(f"[PDF] Build failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF file.")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="omniformat-{format_name.lower().replace(" ", "-")}.pdf"'
        },
    )
