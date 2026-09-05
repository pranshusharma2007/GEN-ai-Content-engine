"""
OmniFormat AI Engine — Backend
SIH26154 · Team WildCard

Architecture:
  source → normalize_source() → extract_ground_truth() → 6 parallel agents
        → verify_claims() → check_cross_format_consistency() → MongoDB → response

Formats: advisory, executive_summary, linkedin, x_thread, presentation, infographic
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
    "infographic",
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


def generate_advisory(source: str, tone: str, audience: str, llm: LLMProvider, ground_truth: str = "") -> dict:
    gt_block = f"\n\nVERIFIED GROUND TRUTH (use only these facts, never invent others):\n{ground_truth}" if ground_truth else ""
    system = textwrap.dedent(f"""
        You are a Senior Strategic Advisor producing a formal advisory bulletin for {audience}.
        Tone: {tone}.

        AUDIENCE GUIDANCE — {audience}:
        - Leadership / Execs: Lead with decision-forcing bottom lines. Risk-weighted, outcome-focused.
        - Stakeholders & Investors: Financial impact first, governance second.
        - General Public: Accessible language, real-world consequences, no jargon.
        - Tech / Developers: Implementation details, technical risks, system implications.
        - Sales / Marketing: Opportunity framing, competitive implications, market positioning.

        Structure your advisory with these exact sections:
        1. EXECUTIVE SUMMARY (2–3 sentences — the single most important takeaway)
        2. SITUATION OVERVIEW (what is happening and why it matters)
        3. THREAT / OPPORTUNITY ASSESSMENT (quantified if possible)
        4. STRATEGIC IMPERATIVES (numbered list — what must be done)
        5. GOVERNANCE & IMPLEMENTATION GUIDANCE (who owns what)
        6. RECOMMENDED ACTIONS (step-by-step roadmap with owners and timelines)
        7. CONCLUSION (single decisive closing statement)

        Rules:
        - Professional, formal register. No emojis.
        - Output plain text (no markdown bold/italics).
        - Every section heading in ALL CAPS followed by a colon.
        - STRICT GROUNDING: Use only facts from the supplied source.{gt_block}
        - NEVER invent or fabricate facts, metrics, organizations, or events.
        - INSUFFICIENT OR VAGUE SOURCE: If the source lacks sufficient factual substance:
          * NEVER invent fictional companies, case studies, or scenarios.
          * Provide a structured advisory template with explicit bracketed placeholders
            (e.g., [Organization/Company], [Specific Threat/Opportunity], [Key Metric], [Recommended Action])
          * Or return "Insufficient source information: Please provide contextual background and data."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the advisory now:"
    content = llm.chat(system, user, temperature=0.35)
    return {"content": _strip_emojis(content)}


def generate_executive_summary(source: str, tone: str, audience: str, llm: LLMProvider, ground_truth: str = "") -> dict:
    gt_block = f"\n\nVERIFIED GROUND TRUTH (use only these facts, never invent others):\n{ground_truth}" if ground_truth else ""
    system = textwrap.dedent(f"""
        You are an Executive Communications Specialist producing a concise executive summary for {audience}.
        Tone: {tone}.

        AUDIENCE GUIDANCE — {audience}:
        - Leadership / Execs: Decision-metrics first (ROI, risk, timeline). Dense, 3-minute read.
        - Stakeholders & Investors: Financial KPIs, growth trajectory, risk exposure.
        - Tech / Developers: Technical findings, system implications, engineering actions.
        - Sales / Marketing: Market signals, customer impact, opportunity sizing.
        - General Public: Plain language, what this means for everyday life.

        Structure (use these exact headings in ALL CAPS):
        1. CONTEXT & BACKGROUND (1–2 sentences — set the scene)
        2. KEY FINDINGS (3–5 punchy bullet points with — prefix)
        3. STRATEGIC IMPLICATIONS (what this means for the organization)
        4. RISK CONSIDERATIONS (what could go wrong and likelihood)
        5. RECOMMENDED ACTIONS (4–6 concrete, owner-assigned actions)

        Rules:
        - Be dense and precise. No filler phrases. No emojis.
        - Output plain text only.
        - STRICT GROUNDING: Use only facts from the source.{gt_block}
        - NEVER fabricate metrics, initiatives, or company names.
        - INSUFFICIENT OR VAGUE SOURCE: If the source lacks sufficient factual data:
          * NEVER invent fictional achievements or operational details.
          * Provide a structured template using bracketed placeholders
            (e.g., [Initiative/Project], [Key Finding], [Metric/KPI], [Action Owner])
          * Or return "Insufficient source information: Please provide detailed report content."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the executive summary now:"
    content = llm.chat(system, user, temperature=0.3)
    return {"content": _strip_emojis(content)}


def generate_linkedin(source: str, tone: str, audience: str, llm: LLMProvider, ground_truth: str = "") -> dict:
    gt_block = f"\n\nVERIFIED GROUND TRUTH (use only these facts, never invent others):\n{ground_truth}" if ground_truth else ""
    system = textwrap.dedent(f"""
        You are a LinkedIn content strategist writing a high-engagement professional post.
        Tone: {tone}. Target Audience: {audience}.

        AUDIENCE GUIDANCE — {audience}:
        - Leadership / Execs: Strategic insight, thought leadership angle.
        - Tech / Developers: Technical credibility, innovation narrative.
        - Sales / Marketing: Problem-solution framing, commercial angle.
        - General Public: Relatable story, accessible insight.
        - Stakeholders & Investors: Business impact, opportunity signal.

        Structure (follow exactly in this order):
        1. HOOK LINE (first sentence alone — bold, attention-grabbing, stands on its own)
        [blank line]
        2. 2–3 lines of story, context, or surprising fact from the source
        [blank line]
        3. 3–5 key insights — each on its own line, prefixed with "—"
        [blank line]
        4. Key takeaway (1–2 sentences — the lesson or "so what")
        [blank line]
        5. Closing question (1 sentence — thought-provoking, invites comments)
        [blank line]
        6. 3–5 relevant hashtags on the final line

        Rules:
        - NEVER use emojis.
        - 150–250 words total.
        - Conversational but professional. First-person voice when appropriate.
        - STRICT GROUNDING: NEVER invent factual details absent from the source.{gt_block}
        - Do NOT invent company names, job titles, career achievements, or personal background.
        - INSUFFICIENT OR VAGUE SOURCE (e.g., "give joining post", "write announcement"):
          * NEVER invent fictional details to fill gaps.
          * Return a useful template with clear bracketed placeholders:
            [Company Name], [Role], [Name], [Key Responsibility], [Previous Experience], [Key Goal/Achievement]
          * Or return "Insufficient source information" and list exactly what details are needed.
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the LinkedIn post now:"
    content = llm.chat(system, user, temperature=0.35)
    return {"content": _strip_emojis(content)}


def generate_x_thread(source: str, tone: str, audience: str, llm: LLMProvider, ground_truth: str = "") -> dict:
    gt_block = f"\n\nVERIFIED GROUND TRUTH (use only these facts, never invent others):\n{ground_truth}" if ground_truth else ""
    system = textwrap.dedent(f"""
        You are a social media strategist writing a punchy, viral X/Twitter thread.
        Tone: {tone}. Target Audience: {audience}.

        AUDIENCE GUIDANCE — {audience}:
        - Leadership / Execs: Strategic insight, market signals, authority voice.
        - Tech / Developers: Technical facts, code implications, innovation angle.
        - Sales / Marketing: Trends, competitive signals, opportunity framing.
        - General Public: Surprising facts, relatable impact, plain language.
        - Stakeholders & Investors: Numbers-first, signal vs noise, market implications.

        Structure (follow exactly):
        Tweet 1/N: HOOK — bold, surprising, or contrarian opening. Standalone. Max 280 chars.
        Tweet 2/N: Context — the "here's why this matters" setup.
        Tweet 3/N through penultimate: One self-contained insight per tweet.
          Each starts with its number (e.g., "3/7:"). Max 280 chars each.
        Final tweet: Crisp recap + direct call to action + 2–3 relevant hashtags.

        Rules:
        - Generate 5–8 tweets total.
        - Each tweet MUST be ≤ 280 characters (count carefully).
        - No emojis. Punchy, active voice.
        - Separate tweets with a blank line.
        - STRICT GROUNDING: Only facts from the source.{gt_block}
        - NEVER invent fictional organizations, statistics, or stories.
        - INSUFFICIENT OR VAGUE SOURCE: If the source lacks sufficient detail:
          * Do NOT invent fictional facts.
          * Return a thread template with bracketed placeholders
            (e.g., [Topic/Announcement], [Key Stat], [Takeaway], [Call to Action])
          * Or return "Insufficient source information: Please provide source material."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the X/Twitter thread now:"
    content = llm.chat(system, user, temperature=0.35)
    return {"content": _strip_emojis(content)}


def generate_presentation(source: str, tone: str, audience: str, llm: LLMProvider, ground_truth: str = "") -> dict:
    gt_block = f"\n\nVERIFIED GROUND TRUTH (use only these facts, never invent others):\n{ground_truth}" if ground_truth else ""
    system = textwrap.dedent(f"""
        You are a senior presentation designer creating a structured, audience-optimized slide deck.
        Tone: {tone}. Target Audience: {audience}.

        AUDIENCE GUIDANCE — {audience}:
        - Leadership / Execs: Decision-ready slides. Bottom line up front. Metrics-heavy.
        - Tech / Developers: Architecture diagrams described in text, implementation steps, technical depth.
        - Stakeholders & Investors: Financial projections, growth narrative, risk/return.
        - Sales / Marketing: Problem-solution arc, competitive landscape, customer wins.
        - General Public: Clear narrative, minimal jargon, visual storytelling hints.

        For each slide output EXACTLY:
        SLIDE [N]: [Title]
        BULLETS:
        — [bullet 1 — one idea per bullet, speaker-scannable]
        — [bullet 2]
        — [bullet 3]
        SPEAKER NOTES: [2–3 sentences — what the presenter says, not what's on screen]

        Requirements:
        - SLIDE 1: Title slide — presentation title + subtitle + context line
        - SLIDES 2–(N-1): Content slides — one key theme per slide, 3–5 bullets
        - FINAL SLIDE: Conclusion — Key Takeaways + Immediate Next Steps

        Rules:
        - 7–10 slides total.
        - 3–5 bullets per content slide. Each bullet ≤ 12 words.
        - No emojis. Plain text only.
        - STRICT GROUNDING: Only facts from the source.{gt_block}
        - NEVER fabricate statistics, company names, or case studies.
        - INSUFFICIENT OR VAGUE SOURCE: If the source lacks detail:
          * Do NOT invent fictional entities or data.
          * Provide a slide outline template using bracketed placeholders
            (e.g., [Company/Topic], [Key Finding], [Metric], [Owner])
          * Or return "Insufficient source information: Please provide topic details."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the presentation outline now:"
    content = llm.chat(system, user, temperature=0.35)
    return {"content": _strip_emojis(content), "_raw_outline": content}


def generate_infographic(source: str, tone: str, audience: str, llm: LLMProvider, ground_truth: str = "") -> dict:
    gt_block = f"\n\nVERIFIED GROUND TRUTH (use only these facts, never invent others):\n{ground_truth}" if ground_truth else ""
    system = textwrap.dedent(f"""
        You are a data visualization specialist creating structured infographic data.
        Tone: {tone}. Target Audience: {audience}.

        AUDIENCE GUIDANCE — {audience}:
        - Leadership / Execs: KPIs and outcomes front and center. Minimal text, maximum signal.
        - Tech / Developers: Technical metrics, performance benchmarks, architecture highlights.
        - Stakeholders & Investors: Financial metrics, growth rates, market data.
        - Sales / Marketing: Market share, customer metrics, competitive data.
        - General Public: Simple statistics, relatable comparisons, clear visual hierarchy.

        Output ONLY a valid JSON object with this exact structure (no markdown fences):
        {{
          "title": "Short, punchy infographic title (max 10 words)",
          "subtitle": "One-line explanatory subtitle (max 20 words)",
          "key_stats": [
            {{"label": "...", "value": "...", "unit": "..."}},
            {{"label": "...", "value": "...", "unit": "..."}}
          ],
          "sections": [
            {{"heading": "...", "points": ["...", "...", "..."]}}
          ],
          "chart": {{
            "type": "bar",
            "title": "...",
            "labels": ["...", "..."],
            "values": [0, 0]
          }},
          "source_note": "Data derived from: [brief source description]"
        }}

        Rules for key_stats: Extract 3–6 real statistics or metrics from the source.
        Rules for sections: 2–4 sections with 2–4 points each.
        Rules for chart: type must be "bar", "pie", or "line". Use real data from source.
        STRICT GROUNDING:{gt_block}
        - NEVER invent statistics, percentages, or data not in the source.
        - INSUFFICIENT OR VAGUE SOURCE: If the source lacks quantitative data:
          * Use placeholders: {{"label": "[Metric Name]", "value": "[N/A]", "unit": ""}}
          * Set chart values to [] and labels to []
          * Add a note in source_note: "Insufficient source data — please provide content with metrics."
    """).strip()

    user = f"Source:\n{source}\n\nGenerate the infographic JSON now:"
    raw = llm.chat(system, user, temperature=0.25)
    # Parse JSON robustly
    try:
        data = _extract_json_block(raw)
        # Ensure required keys exist
        data.setdefault("title", "Infographic")
        data.setdefault("subtitle", "")
        data.setdefault("key_stats", [])
        data.setdefault("sections", [])
        data.setdefault("chart", {"type": "bar", "title": "", "labels": [], "values": []})
        data.setdefault("source_note", "")
        return {"content": json.dumps(data), "_infographic_data": data}
    except Exception as exc:
        print(f"[Infographic] JSON parse failed: {exc}")
        fallback = {
            "title": "Infographic",
            "subtitle": "Could not parse structured data from source",
            "key_stats": [],
            "sections": [{"heading": "Raw Output", "points": [raw[:500]]}],
            "chart": {"type": "bar", "title": "", "labels": [], "values": []},
            "source_note": "Parsing error — raw LLM output included above.",
        }
        return {"content": json.dumps(fallback), "_infographic_data": fallback}


# ═══════════════════════════════════════════════════════════════════════════════
# Ground Truth Extraction
# ═══════════════════════════════════════════════════════════════════════════════

_GROUND_TRUTH_SYSTEM = textwrap.dedent("""
    You are a fact extraction specialist. Extract structured ground truth from the source text.

    Output ONLY a valid JSON object with this exact structure:
    {
      "entities": ["list of named organizations, people, products, places mentioned"],
      "key_facts": ["list of key factual statements (max 10, each ≤ 30 words)"],
      "statistics": [
        {"metric": "what is being measured", "value": "the number/amount", "unit": "unit of measurement or empty string"}
      ],
      "timeline": [
        {"date": "date or period", "event": "what happened"}
      ]
    }

    Rules:
    - Extract ONLY what is explicitly stated. NEVER infer or invent.
    - If a category has no entries, return an empty list [].
    - statistics: only include if actual numbers/percentages/amounts are present.
    - Output raw JSON only — no markdown fences, no explanation.
""").strip()


def extract_ground_truth(source: str, llm: LLMProvider) -> dict:
    """Extract structured ground truth facts from the normalized source."""
    user = f"SOURCE:\n{source[:6000]}\n\nExtract ground truth now:"
    try:
        raw = llm.chat(_GROUND_TRUTH_SYSTEM, user, temperature=0.1)
        result = _extract_json_block(raw)
        result.setdefault("entities", [])
        result.setdefault("key_facts", [])
        result.setdefault("statistics", [])
        result.setdefault("timeline", [])
        return result
    except Exception as exc:
        print(f"[GroundTruth] Extraction failed: {exc}")
        return {"entities": [], "key_facts": [], "statistics": [], "timeline": []}


def _format_ground_truth(gt: dict) -> str:
    """Format ground truth dict as a compact string for injection into agent prompts."""
    lines = []
    if gt.get("entities"):
        lines.append("Entities: " + ", ".join(gt["entities"][:10]))
    if gt.get("key_facts"):
        lines.append("Key facts:")
        for f in gt["key_facts"][:8]:
            lines.append(f"  - {f}")
    if gt.get("statistics"):
        lines.append("Statistics:")
        for s in gt["statistics"][:6]:
            unit = f" {s.get('unit', '')}" if s.get('unit') else ""
            lines.append(f"  - {s.get('metric', '')}: {s.get('value', '')}{unit}")
    if gt.get("timeline"):
        lines.append("Timeline:")
        for t in gt["timeline"][:5]:
            lines.append(f"  - {t.get('date', '')}: {t.get('event', '')}")
    return "\n".join(lines) if lines else ""


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
    "infographic": generate_infographic,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-Format Consistency Checker
# ═══════════════════════════════════════════════════════════════════════════════

_CONSISTENCY_SYSTEM = textwrap.dedent("""
    You are a cross-document consistency auditor.
    You will be given multiple AI-generated outputs (each labeled by format name).
    Your job is to detect factual contradictions between them.

    Output ONLY a valid JSON object with this exact structure:
    {
      "contradictions": [
        {
          "formats": ["format_a", "format_b"],
          "claim_a": "exact claim from format_a",
          "claim_b": "conflicting claim from format_b",
          "severity": "high"
        }
      ],
      "consistency_score": 95
    }

    severity levels: "high" (direct factual conflict), "medium" (ambiguous/inconsistent framing), "low" (minor phrasing difference)
    consistency_score: 0–100, where 100 = perfectly consistent, 0 = severe contradictions throughout.

    Rules:
    - Only flag FACTUAL contradictions (different numbers, dates, entity names, outcomes).
    - Do NOT flag stylistic differences or format-appropriate restructuring.
    - If no contradictions found, return {"contradictions": [], "consistency_score": 100}.
    - Output raw JSON only — no markdown fences, no explanation.
""").strip()


def check_cross_format_consistency(results: dict, llm: LLMProvider) -> dict:
    """Detect factual contradictions across all successfully generated formats."""
    successful = {
        fmt: data["content"]
        for fmt, data in results.items()
        if data.get("status") == "success" and data.get("content")
        and fmt != "infographic"  # skip infographic JSON
    }
    if len(successful) < 2:
        return {"contradictions": [], "consistency_score": 100}

    # Build a compact multi-document input
    doc_blocks = []
    for fmt, content in successful.items():
        truncated = content[:1500]
        doc_blocks.append(f"=== {fmt.upper().replace('_', ' ')} ===\n{truncated}")
    combined = "\n\n".join(doc_blocks)

    user = f"GENERATED OUTPUTS TO CHECK:\n\n{combined}\n\nDetect contradictions now:"
    try:
        raw = llm.chat(_CONSISTENCY_SYSTEM, user, temperature=0.1)
        result = _extract_json_block(raw)
        result.setdefault("contradictions", [])
        result.setdefault("consistency_score", 100)
        # Clamp score
        result["consistency_score"] = max(0, min(100, int(result["consistency_score"])))
        return result
    except Exception as exc:
        print(f"[Consistency] Check failed: {exc}")
        return {"contradictions": [], "consistency_score": 100, "error": "Consistency check could not be completed."}


async def _run_agent(
    fmt: str,
    source: str,
    tone: str,
    audience: str,
    llm: LLMProvider,
    ground_truth: str = "",
) -> tuple[str, dict]:
    """Run one generation agent + verification. Returns (format, result_dict)."""
    fn = FORMAT_FN_MAP[fmt]
    try:
        gen_result = await run_in_threadpool(fn, source, tone, audience, llm, ground_truth)
        content = gen_result.get("content", "")
        infographic_data = gen_result.get("_infographic_data")  # only for infographic
        # Verify generated content against source
        verification = await run_in_threadpool(verify_claims, source, content, llm)
        result: dict = {
            "status": "success",
            "content": content,
            "verification": verification,
        }
        if infographic_data is not None:
            result["infographic_data"] = infographic_data
        return fmt, result
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
    ground_truth: str = "",
) -> dict:
    """Run all selected format agents concurrently. One failure ≠ all fail."""
    tasks = [
        _run_agent(fmt, source, tone, audience, llm, ground_truth)
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
                "consistency.consistency_score": 1,
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

    # ── Extract ground truth (single pass, injected into all agents) ──────
    gt_dict = await run_in_threadpool(extract_ground_truth, normalized_source, llm)
    ground_truth_str = _format_ground_truth(gt_dict)
    print(f"[GroundTruth] Entities={len(gt_dict['entities'])} Facts={len(gt_dict['key_facts'])} Stats={len(gt_dict['statistics'])}")

    # ── Run agents concurrently ───────────────────────────────────────────
    results = await run_agents_concurrently(
        formats=fmt_list,
        source=normalized_source,
        tone=tone,
        audience=audience,
        llm=llm,
        ground_truth=ground_truth_str,
    )

    # ── Cross-format consistency check ────────────────────────────────────
    consistency = await run_in_threadpool(check_cross_format_consistency, results, llm)
    print(f"[Consistency] Score={consistency.get('consistency_score')} Contradictions={len(consistency.get('contradictions', []))}")

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
        "ground_truth": gt_dict,
        "consistency": consistency,
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
        "ground_truth": gt_dict,
        "consistency": consistency,
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


# ── Source Version Comparison ─────────────────────────────────────────────────

@app.post("/compare_versions")
@app.post("/api/compare_versions")
async def compare_versions(request: Request):
    """Compare two source versions and identify changed facts."""
    body = await request.json()
    source_v1 = (body.get("source_v1") or "").strip()
    source_v2 = (body.get("source_v2") or "").strip()
    if not source_v1 or not source_v2:
        raise HTTPException(status_code=400, detail="Both source_v1 and source_v2 are required.")

    try:
        llm = get_llm()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    _DIFF_SYSTEM = textwrap.dedent("""
        You are a source-change analyst. You will receive two versions of a source document.
        Identify what has changed between V1 and V2 in terms of facts, entities, and data.

        Output ONLY valid JSON:
        {
          "added": ["new facts or data present in V2 but not V1"],
          "removed": ["facts present in V1 but removed in V2"],
          "changed_facts": [
            {"fact": "what changed", "v1_value": "...", "v2_value": "..."}
          ],
          "affected_formats": ["list of format names that should be regenerated"]
        }

        affected_formats must be a subset of: advisory, executive_summary, linkedin, x_thread, presentation, infographic
        If a change primarily affects statistics → advisory, executive_summary, infographic
        If a change affects tone/narrative → linkedin, x_thread
        If structural changes → presentation
        Output raw JSON only.
    """).strip()

    user = f"SOURCE V1:\n{source_v1[:4000]}\n\nSOURCE V2:\n{source_v2[:4000]}\n\nAnalyze changes:"
    try:
        raw = await run_in_threadpool(llm.chat, _DIFF_SYSTEM, user, 0.1)
        result = _extract_json_block(raw)
        result.setdefault("added", [])
        result.setdefault("removed", [])
        result.setdefault("changed_facts", [])
        result.setdefault("affected_formats", [])
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Version comparison failed: {exc}")


# ── Surgical Regeneration ─────────────────────────────────────────────────────

@app.post("/regenerate")
@app.post("/api/regenerate")
async def regenerate(request: Request):
    """Regenerate only specified formats for an existing run with updated source."""
    body = await request.json()
    run_id_ref = (body.get("run_id") or "").strip()
    new_source = (body.get("source") or "").strip()
    fmt_list_raw = body.get("formats") or []
    tone = (body.get("tone") or "Professional").strip()
    audience = (body.get("audience") or "Leadership / Execs").strip()

    if not new_source:
        raise HTTPException(status_code=400, detail="source is required.")
    if not isinstance(fmt_list_raw, list) or not fmt_list_raw:
        raise HTTPException(status_code=400, detail="formats must be a non-empty list.")

    invalid = [f for f in fmt_list_raw if f not in SUPPORTED_FORMATS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported format(s): {invalid}")
    if tone not in SUPPORTED_TONES:
        raise HTTPException(status_code=400, detail="Unsupported tone.")
    if audience not in SUPPORTED_AUDIENCES:
        raise HTTPException(status_code=400, detail="Unsupported audience.")

    normalized_source = _normalize_text(new_source)

    try:
        llm = get_llm()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # Extract fresh ground truth for the new source
    gt_dict = await run_in_threadpool(extract_ground_truth, normalized_source, llm)
    ground_truth_str = _format_ground_truth(gt_dict)

    # Regenerate only selected formats
    new_results = await run_agents_concurrently(
        formats=fmt_list_raw,
        source=normalized_source,
        tone=tone,
        audience=audience,
        llm=llm,
        ground_truth=ground_truth_str,
    )

    # Check consistency of newly generated formats
    consistency = await run_in_threadpool(check_cross_format_consistency, new_results, llm)

    # Merge with existing run if run_id_ref provided
    existing_run = None
    if run_id_ref:
        existing_run = await run_in_threadpool(_fetch_run, run_id_ref)

    merged_results = dict(existing_run.get("results", {})) if existing_run else {}
    merged_results.update(new_results)

    # Save as a new run
    new_run_id = str(uuid.uuid4())
    preview = normalized_source[:300] + "..." if len(normalized_source) > 300 else normalized_source
    document = {
        "run_id": new_run_id,
        "parent_run_id": run_id_ref or None,
        "source": {
            "type": "text",
            "content": normalized_source[:50000],
            "preview": preview,
            "url": None,
        },
        "parameters": {"formats": fmt_list_raw, "tone": tone, "audience": audience},
        "ground_truth": gt_dict,
        "consistency": consistency,
        "results": merged_results,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "regenerated_formats": fmt_list_raw,
    }
    await run_in_threadpool(_save_to_mongo, document)

    return {
        "run_id": new_run_id,
        "parent_run_id": run_id_ref or None,
        "ground_truth": gt_dict,
        "consistency": consistency,
        "results": merged_results,
        "regenerated_formats": fmt_list_raw,
    }


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
