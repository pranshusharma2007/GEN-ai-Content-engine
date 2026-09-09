"""
OmniFormat AI Engine — Backend
SIH26154 · Team WildCard

Architecture:
  source → normalize_source() → extract_ground_truth() → 6 parallel agents
        → verify_claims() → check_cross_format_consistency() → storage (Supabase) → response

Formats: advisory, executive_summary, linkedin, x_thread, presentation, infographic
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import ipaddress
import json
import os
import re
import textwrap
import uuid
import zipfile
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

# ── Load environment ─────────────────────────────────────────────────────────
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)
load_dotenv()  # local fallback

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from auth import get_current_user

# ── Configuration ─────────────────────────────────────────────────────────────
FRONTEND_ORIGINS = [
    x.strip()
    for x in os.environ.get(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    if x.strip()
]

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
# Gemini "flash" models reason by default; for these structured tasks that is pure
# latency. 0 = thinking off. Raise (e.g. 512) only if output quality needs it.
GEMINI_THINKING_BUDGET = int(os.environ.get("GEMINI_THINKING_BUDGET", "0"))
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")  # default provider for generation

# Task → preferred provider for the shared analysis passes (not per-format generation).
# Default to Groq for these — they run in series around the parallel agents, so
# latency here is on the critical path. Each falls back to the other on failure.
TASK_PROVIDER = {
    "ground_truth": os.environ.get("LLM_TASK_GROUND_TRUTH", "groq"),
    "verify": os.environ.get("LLM_TASK_VERIFY", "groq"),
    "consistency": os.environ.get("LLM_TASK_CONSISTENCY", "groq"),
    "diff": os.environ.get("LLM_TASK_DIFF", "groq"),
}

# Per-format generation routing. Each selected format's agent runs on its assigned
# provider; the source input is identical for all. Override any of these via env.
# MVP providers: "groq" | "gemini" (falls back to the other if the primary fails).
FORMAT_PROVIDER = {
    "advisory":          os.environ.get("LLM_FORMAT_ADVISORY", "gemini"),
    "executive_summary": os.environ.get("LLM_FORMAT_EXECUTIVE_SUMMARY", "gemini"),
    "linkedin":          os.environ.get("LLM_FORMAT_LINKEDIN", "groq"),
    "x_thread":          os.environ.get("LLM_FORMAT_X_THREAD", "groq"),
    "presentation":      os.environ.get("LLM_FORMAT_PRESENTATION", "gemini"),
    "infographic":       os.environ.get("LLM_FORMAT_INFOGRAPHIC", "gemini"),
}

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

@asynccontextmanager
async def lifespan(_app: "FastAPI"):
    providers = _available_providers()
    if not providers:
        print("[WARN] No LLM provider configured (set GROQ_API_KEY and/or GEMINI_API_KEY).")
    else:
        print(f"[OmniFormat] LLM providers: {providers}")
        print(f"[OmniFormat] Per-format routing: {FORMAT_PROVIDER}")
        print(f"[OmniFormat] Task routing: {TASK_PROVIDER}")
    print(f"[OmniFormat] History backend: {storage.backend_label()}")
    print("[OmniFormat] Backend started.")
    yield


app = FastAPI(title="OmniFormat AI Engine", version="2.2.0", lifespan=lifespan)

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


def _retry_after_seconds(message: str, default: float = 2.0) -> float:
    """Pull 'try again in 1.2s' / 'retry after 3' hints out of a rate-limit message."""
    m = re.search(r"(?:try again in|retry after)\s+([\d.]+)\s*(ms|s)?", message, re.I)
    if not m:
        return default
    val = float(m.group(1))
    return val / 1000.0 if (m.group(2) or "").lower() == "ms" else val


class GroqAdapter(LLMProvider):
    """Groq-hosted LLM adapter with model discovery, 429 backoff, and fallback."""

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
        import time as _time

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_err = None
        for model in self._models:
            for attempt in range(3):  # one model, up to 3 tries (429 backoff)
                try:
                    resp = self._client.chat.completions.create(
                        messages=messages, model=model, temperature=temperature,
                    )
                    return resp.choices[0].message.content or ""
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
                    msg = str(exc)
                    is_rate = "429" in msg or "rate_limit" in msg.lower()
                    if is_rate and attempt < 2:
                        wait = _retry_after_seconds(msg, default=2.0 * (attempt + 1))
                        print(f"[GroqAdapter] {model} rate-limited; retrying in {wait:.1f}s")
                        _time.sleep(min(wait, 8.0))
                        continue
                    print(f"[GroqAdapter] model={model} failed: {exc}")
                    break  # move to next model
        raise RuntimeError(f"All Groq models failed. Last error: {last_err}")


class GeminiAdapter(LLMProvider):
    """Google Gemini adapter (google-genai SDK)."""

    def __init__(self, api_key: str, model: str = GEMINI_MODEL) -> None:
        from google import genai
        from google.genai import types

        timeout_ms = int(os.environ.get("GEMINI_TIMEOUT_MS", "30000"))
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        self._model = model

    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        from google.genai import types

        cfg = dict(
            system_instruction=system,
            temperature=temperature,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_budget=GEMINI_THINKING_BUDGET),
        )
        try:
            resp = self._client.models.generate_content(
                model=self._model, contents=user,
                config=types.GenerateContentConfig(**cfg),
            )
        except Exception as exc:  # noqa: BLE001
            # Only retry when the *thinking knob* is the problem; let timeouts /
            # auth / quota errors propagate fast so _RoutedLLM can fall back.
            if "thinking" not in str(exc).lower():
                raise
            cfg.pop("thinking_config", None)
            resp = self._client.models.generate_content(
                model=self._model, contents=user,
                config=types.GenerateContentConfig(**cfg),
            )
        return getattr(resp, "text", "") or ""


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


# ── Provider registry + task router ──────────────────────────────────────────

_ADAPTERS: dict[str, Optional[LLMProvider]] = {}


def _get_adapter(name: str) -> Optional[LLMProvider]:
    """Lazily build and cache one provider adapter. Returns None if unconfigured."""
    name = name.lower()
    if name in _ADAPTERS:
        return _ADAPTERS[name]
    adapter: Optional[LLMProvider] = None
    try:
        if name == "groq" and GROQ_API_KEY:
            adapter = GroqAdapter(api_key=GROQ_API_KEY)
        elif name == "gemini" and GEMINI_API_KEY:
            adapter = GeminiAdapter(api_key=GEMINI_API_KEY)
        elif name == "ollama":
            adapter = OllamaAdapter()
    except Exception as exc:  # noqa: BLE001
        print(f"[LLM] Failed to build adapter {name!r}: {exc}")
        adapter = None
    _ADAPTERS[name] = adapter
    return adapter


def _available_providers() -> list[str]:
    out = []
    if GROQ_API_KEY:
        out.append("groq")
    if GEMINI_API_KEY:
        out.append("gemini")
    return out


class _RoutedLLM(LLMProvider):
    """Sends to a preferred provider, with automatic fallback to any other
    configured provider if the primary call fails. `last_provider` records which
    provider actually served the most recent call."""

    def __init__(self, preferred: str, label: str) -> None:
        self._label = label
        preferred = (preferred or LLM_PROVIDER).lower()
        order = [preferred] + [p for p in ("groq", "gemini") if p != preferred]
        self._order = [p for p in order if p in _available_providers()]
        self.last_provider: Optional[str] = None

    @property
    def preferred(self) -> Optional[str]:
        return self._order[0] if self._order else None

    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        if not self._order:
            raise RuntimeError(
                "No LLM provider configured. Set GROQ_API_KEY and/or GEMINI_API_KEY."
            )
        last_err: Optional[Exception] = None
        for name in self._order:
            adapter = _get_adapter(name)
            if adapter is None:
                continue
            try:
                out = adapter.chat(system, user, temperature)
                self.last_provider = name
                return out
            except Exception as exc:  # noqa: BLE001
                print(f"[LLM:{self._label}] provider={name} failed: {exc}")
                last_err = exc
        raise RuntimeError(f"All providers failed for {self._label!r}. Last error: {last_err}")


_ROUTED: dict[str, _RoutedLLM] = {}


def get_llm_for(task: str) -> LLMProvider:
    """Task-routed LLM for the shared analysis passes (ground_truth | verify | consistency | diff)."""
    key = f"task:{task}"
    if key not in _ROUTED:
        _ROUTED[key] = _RoutedLLM(TASK_PROVIDER.get(task, LLM_PROVIDER), task)
    return _ROUTED[key]


def get_llm_for_format(fmt: str) -> _RoutedLLM:
    """Per-format generation LLM. Each selected format's agent runs on its assigned provider."""
    key = f"fmt:{fmt}"
    if key not in _ROUTED:
        _ROUTED[key] = _RoutedLLM(FORMAT_PROVIDER.get(fmt, LLM_PROVIDER), f"gen:{fmt}")
    return _ROUTED[key]


def get_llm() -> LLMProvider:
    """Back-compat helper — the default provider."""
    return _RoutedLLM(LLM_PROVIDER, "default")


# ═══════════════════════════════════════════════════════════════════════════════
# History persistence — see storage.py (Supabase + local-JSON fallback)
# ═══════════════════════════════════════════════════════════════════════════════

import storage  # noqa: E402


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


# ═══════════════════════════════════════════════════════════════════════════════
# Tamper-Evident Integrity (SHA-256 hash-logging)
# ═══════════════════════════════════════════════════════════════════════════════

HASH_ALGO = "sha256"


def _sha256(text: str) -> str:
    """SHA-256 hex digest of a string (UTF-8). Empty/None → hash of ''."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _run_fingerprint(run_id: str, created_at: str, results: dict) -> str:
    """A single fingerprint over a whole run: run_id + timestamp + each format's
    content hash, in a stable order. Any change to any output changes this."""
    parts = [run_id or "", created_at or ""]
    for fmt in sorted(results):
        entry = results[fmt] or {}
        parts.append(f"{fmt}:{entry.get('hash', '')}")
    return _sha256("|".join(parts))


async def _run_agent(
    fmt: str,
    source: str,
    tone: str,
    audience: str,
    ground_truth: str = "",
) -> tuple[str, dict]:
    """Run one generation agent (on its assigned provider) + verification.
    Returns (format, result_dict). Same source input for every format."""
    fn = FORMAT_FN_MAP[fmt]
    assigned = FORMAT_PROVIDER.get(fmt, LLM_PROVIDER)
    try:
        gen_llm = get_llm_for_format(fmt)
        gen_result = await run_in_threadpool(fn, source, tone, audience, gen_llm, ground_truth)
        content = gen_result.get("content", "")
        infographic_data = gen_result.get("_infographic_data")  # only for infographic
        # Verify generated content against source (task-routed — prefers Gemini)
        verification = await run_in_threadpool(
            verify_claims, source, content, get_llm_for("verify")
        )
        served_by = (
            getattr(gen_llm, "last_provider", None)
            or getattr(gen_llm, "preferred", None)
            or assigned
        )
        result: dict = {
            "status": "success",
            "content": content,
            "verification": verification,
            "provider": {"assigned": assigned, "served_by": served_by},
            # Fingerprint of the exact content string, recorded at generation time.
            "hash": _sha256(content),
            "hash_algo": HASH_ALGO,
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
            "provider": {"assigned": assigned, "served_by": None},
        }


async def run_agents_concurrently(
    formats: list[str],
    source: str,
    tone: str,
    audience: str,
    ground_truth: str = "",
) -> dict:
    """Run each selected format's agent concurrently on its assigned provider.
    Same source for all; one failure ≠ all fail."""
    routing = {fmt: FORMAT_PROVIDER.get(fmt, LLM_PROVIDER) for fmt in formats}
    print(f"[Agents] Per-format routing: {routing}")
    tasks = [
        _run_agent(fmt, source, tone, audience, ground_truth)
        for fmt in formats
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return dict(results)


# ═══════════════════════════════════════════════════════════════════════════════
# History Persistence (delegates to storage.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _save_run(document: dict) -> None:
    try:
        storage.save_run(document)
    except Exception as exc:  # noqa: BLE001
        print(f"[storage] Save failed: {exc}")


def _fetch_history(user_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    try:
        return storage.fetch_history(user_id=user_id, limit=limit)
    except Exception as exc:  # noqa: BLE001
        print(f"[storage] History fetch failed: {exc}")
        return []


def _fetch_run(run_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    try:
        return storage.fetch_run(run_id, user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[storage] Fetch run failed: {exc}")
        return None


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
        "version": "2.2.0",
        "llm_providers": _available_providers(),
        "format_routing": FORMAT_PROVIDER,
        "task_routing": TASK_PROVIDER,
        "database": storage.backend_label(),
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
    user: dict = Depends(get_current_user),
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

    # ── LLM routing: per-format generation + task-routed analysis (with fallback) ──
    if not _available_providers():
        raise HTTPException(
            status_code=503,
            detail="No LLM provider configured. Set GROQ_API_KEY and/or GEMINI_API_KEY.",
        )

    # ── Extract ground truth (single pass, injected into all agents) ──────
    gt_dict = await run_in_threadpool(
        extract_ground_truth, normalized_source, get_llm_for("ground_truth")
    )
    ground_truth_str = _format_ground_truth(gt_dict)
    print(f"[GroundTruth] Entities={len(gt_dict['entities'])} Facts={len(gt_dict['key_facts'])} Stats={len(gt_dict['statistics'])}")

    # ── Run the selected format agents concurrently, each on its assigned provider ──
    results = await run_agents_concurrently(
        formats=fmt_list,
        source=normalized_source,
        tone=tone,
        audience=audience,
        ground_truth=ground_truth_str,
    )

    # ── Cross-format consistency check ────────────────────────────────────
    consistency = await run_in_threadpool(
        check_cross_format_consistency, results, get_llm_for("consistency")
    )
    print(f"[Consistency] Score={consistency.get('consistency_score')} Contradictions={len(consistency.get('contradictions', []))}")

    # ── Persist run ───────────────────────────────────────────────────────
    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    run_hash = _run_fingerprint(run_id, created_at, results)
    preview = normalized_source[:300] + "..." if len(normalized_source) > 300 else normalized_source
    document = {
        "run_id": run_id,
        "user_id": user.get("uid", "anonymous"),
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
        "integrity": {"algo": HASH_ALGO, "run_hash": run_hash},
        "created_at": created_at,
    }
    await run_in_threadpool(_save_run, document)

    return {
        "run_id": run_id,
        "source": {
            "type": source_type,
            "preview": preview,
        },
        "ground_truth": gt_dict,
        "consistency": consistency,
        "results": results,
        "integrity": {"algo": HASH_ALGO, "run_hash": run_hash},
        "created_at": created_at,
    }


@app.get("/history")
@app.get("/api/history")
async def get_history(user: dict = Depends(get_current_user)):
    entries = await run_in_threadpool(_fetch_history, user.get("uid"))
    return {"history": entries}


@app.get("/history/{run_id}")
@app.get("/api/history/{run_id}")
async def get_history_item(run_id: str, user: dict = Depends(get_current_user)):
    doc = await run_in_threadpool(_fetch_run, run_id, user.get("uid"))
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found.")
    return doc


# ── Tamper-Evident Integrity Verification ────────────────────────────────────

def _verify_against_run(doc: Optional[dict], fmt: str, content: Optional[str]) -> dict:
    """Compare a SHA-256 of `content` (or the stored content when omitted) against
    the fingerprint recorded for `fmt` at generation time."""
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found.")
    entry = (doc.get("results") or {}).get(fmt)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Format {fmt!r} not in this run.")
    stored_hash = entry.get("hash")
    if not stored_hash:
        raise HTTPException(
            status_code=422,
            detail=f"No integrity fingerprint was recorded for {fmt!r} (older run).",
        )
    check_content = entry.get("content", "") if content is None else content
    computed_hash = _sha256(check_content)
    return {
        "run_id": doc.get("run_id"),
        "format_name": fmt,
        "algo": entry.get("hash_algo", HASH_ALGO),
        "stored_hash": stored_hash,
        "computed_hash": computed_hash,
        "verified": computed_hash == stored_hash,
        "recorded_at": doc.get("created_at"),
        "checked_supplied_content": content is not None,
    }


@app.post("/verify")
@app.post("/api/verify")
async def verify_integrity(request: Request, user: dict = Depends(get_current_user)):
    """Re-hash content and compare to the fingerprint recorded at generation time.
    Body: { run_id, format_name, content? }. Omit `content` to check the stored copy."""
    body = await request.json()
    run_id = (body.get("run_id") or "").strip()
    fmt = (body.get("format_name") or body.get("format") or "").strip()
    content = body.get("content")
    if not run_id or not fmt:
        raise HTTPException(status_code=400, detail="run_id and format_name are required.")
    doc = await run_in_threadpool(_fetch_run, run_id, user.get("uid"))
    return _verify_against_run(doc, fmt, content)


@app.get("/verify/{run_id}/{format_name}")
@app.get("/api/verify/{run_id}/{format_name}")
async def verify_integrity_stored(
    run_id: str, format_name: str, user: dict = Depends(get_current_user)
):
    """Storage-integrity check: re-hash the stored content for one format."""
    doc = await run_in_threadpool(_fetch_run, run_id, user.get("uid"))
    return _verify_against_run(doc, format_name, None)


# ── Source Version Comparison ─────────────────────────────────────────────────

@app.post("/compare_versions")
@app.post("/api/compare_versions")
async def compare_versions(request: Request, _user: dict = Depends(get_current_user)):
    """Compare two source versions and identify changed facts."""
    body = await request.json()
    source_v1 = (body.get("source_v1") or "").strip()
    source_v2 = (body.get("source_v2") or "").strip()
    if not source_v1 or not source_v2:
        raise HTTPException(status_code=400, detail="Both source_v1 and source_v2 are required.")

    if not _available_providers():
        raise HTTPException(status_code=503, detail="No LLM provider configured.")
    llm = get_llm_for("diff")

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

    user_prompt = f"SOURCE V1:\n{source_v1[:4000]}\n\nSOURCE V2:\n{source_v2[:4000]}\n\nAnalyze changes:"
    try:
        raw = await run_in_threadpool(llm.chat, _DIFF_SYSTEM, user_prompt, 0.1)
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
async def regenerate(request: Request, user: dict = Depends(get_current_user)):
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

    if not _available_providers():
        raise HTTPException(status_code=503, detail="No LLM provider configured.")

    # Extract fresh ground truth for the new source
    gt_dict = await run_in_threadpool(
        extract_ground_truth, normalized_source, get_llm_for("ground_truth")
    )
    ground_truth_str = _format_ground_truth(gt_dict)

    # Regenerate only selected formats — each on its assigned provider
    new_results = await run_agents_concurrently(
        formats=fmt_list_raw,
        source=normalized_source,
        tone=tone,
        audience=audience,
        ground_truth=ground_truth_str,
    )

    # Check consistency of newly generated formats
    consistency = await run_in_threadpool(
        check_cross_format_consistency, new_results, get_llm_for("consistency")
    )

    # Merge with existing run if run_id_ref provided
    existing_run = None
    if run_id_ref:
        existing_run = await run_in_threadpool(_fetch_run, run_id_ref, user.get("uid"))

    merged_results = dict(existing_run.get("results", {})) if existing_run else {}
    merged_results.update(new_results)

    # Save as a new run
    new_run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    run_hash = _run_fingerprint(new_run_id, created_at, merged_results)
    preview = normalized_source[:300] + "..." if len(normalized_source) > 300 else normalized_source
    document = {
        "run_id": new_run_id,
        "user_id": user.get("uid", "anonymous"),
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
        "integrity": {"algo": HASH_ALGO, "run_hash": run_hash},
        "created_at": created_at,
        "regenerated_formats": fmt_list_raw,
    }
    await run_in_threadpool(_save_run, document)

    return {
        "run_id": new_run_id,
        "parent_run_id": run_id_ref or None,
        "ground_truth": gt_dict,
        "consistency": consistency,
        "results": merged_results,
        "integrity": {"algo": HASH_ALGO, "run_hash": run_hash},
        "created_at": created_at,
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
    return _normalise_ooxml(buf.getvalue())


def _normalise_ooxml(data: bytes) -> bytes:
    """python-pptx / lxml writes each part's XML declaration with SINGLE quotes
    (<?xml version='1.0' ...?>). PowerPoint and Google Slides tolerate this;
    Apple Keynote rejects the file as "invalid format". Rewrite every part's
    declaration to the double-quoted form, preserving zip order and compression."""
    bad = b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
    good = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    src, out = io.BytesIO(data), io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                content = content.replace(bad, good, 1)
            zi = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            zi.compress_type = item.compress_type
            zi.external_attr = item.external_attr
            zout.writestr(zi, content)
    return out.getvalue()


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
async def export_pptx(request: Request, _user: dict = Depends(get_current_user)):
    body = await request.json()
    content = body.get("content", "")
    run_title = body.get("title", "Presentation")
    if not content:
        raise HTTPException(status_code=400, detail="No content provided.")
    try:
        pptx_bytes = await run_in_threadpool(_build_pptx, content, run_title)
    except Exception as exc:
        import traceback
        print(f"[PPTX] Build failed: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PPTX file: {exc}")
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": 'attachment; filename="omniformat-presentation.pptx"',
            "Content-Length": str(len(pptx_bytes)),
        },
    )


@app.post("/export/pdf")
@app.post("/api/export/pdf")
async def export_pdf(request: Request, _user: dict = Depends(get_current_user)):
    body = await request.json()
    content = body.get("content", "")
    format_name = body.get("format_name", "Document")
    if not content:
        raise HTTPException(status_code=400, detail="No content provided.")
    try:
        pdf_bytes = await run_in_threadpool(_build_pdf, content, format_name)
    except Exception as exc:
        import traceback
        print(f"[PDF] Build failed: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF file: {exc}")
    safe_name = format_name.lower().replace(" ", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="omniformat-{safe_name}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
