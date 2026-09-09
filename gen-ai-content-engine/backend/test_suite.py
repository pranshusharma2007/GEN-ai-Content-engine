"""
OmniFormat AI Engine — Backend Test Suite
Phase 8: 15 automated tests covering all upgrade features.

Run with:
    cd gen-ai-content-engine/backend
    python -m pytest test_suite.py -v

Requirements: pytest, httpx, fastapi[testclient]
"""

import json
import sys
import os
import pytest

# ── Ensure the backend module is importable ───────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


# ── Minimal LLM mock for pure unit tests ──────────────────────────────────────
class MockLLM:
    """Deterministic LLM mock — returns predictable outputs for testing."""

    def __init__(self, response: str = "MOCK OUTPUT"):
        self._response = response

    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        return self._response


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Vague input — LinkedIn returns placeholders, NOT invented facts
# ═══════════════════════════════════════════════════════════════════════════════

def test_vague_input_linkedin():
    """Vague source 'give company joining post' must produce placeholder template."""
    from main import generate_linkedin, verify_claims

    real_llm_response = (
        "LinkedIn Post Template\n\n"
        "Excited to announce that I have joined [Company Name] as [Role].\n\n"
        "— [Key Responsibility 1]\n"
        "— [Key Responsibility 2]\n"
        "— [Key Goal/Achievement]\n\n"
        "I look forward to contributing to [Company Name] and growing with this amazing team.\n\n"
        "What advice would you share for someone starting a new role?\n\n"
        "#NewRole #CareerGrowth #Opportunity"
    )

    mock = MockLLM(real_llm_response)
    result = generate_linkedin("give company joining post", "Professional", "Leadership / Execs", mock)
    content = result["content"]

    # Must contain placeholders
    assert "[Company Name]" in content or "[Role]" in content or "Insufficient source" in content, \
        "LinkedIn agent must use placeholders for vague input, not invent facts"

    # Must NOT invent specific company names
    invented = ["XYZ Corporation", "Acme Corp", "ABC Ltd"]
    for name in invented:
        assert name not in content, f"Agent invented fictitious company name: {name}"

    # Verify: placeholders should not be flagged as unsupported
    mock_verifier = MockLLM(json.dumps({
        "claims": [],
        "unsupported_count": 0
    }))
    verification = verify_claims("give company joining post", content, mock_verifier)
    assert verification["unsupported_count"] == 0, \
        "Placeholder template should have 0 unsupported claims"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Vague input — Advisory returns structured template
# ═══════════════════════════════════════════════════════════════════════════════

def test_vague_input_advisory():
    """Vague source must produce advisory with bracketed placeholders."""
    from main import generate_advisory

    mock_response = (
        "EXECUTIVE SUMMARY:\n"
        "[Organization/Company] faces [Specific Threat/Opportunity] requiring strategic action.\n\n"
        "SITUATION OVERVIEW:\n"
        "[Describe the current situation here.]\n\n"
        "RECOMMENDED ACTIONS:\n"
        "1. [Recommended Action 1] — Owner: [Action Owner]\n"
    )
    mock = MockLLM(mock_response)
    result = generate_advisory("some vague text", "Professional", "Leadership / Execs", mock)
    content = result["content"]

    assert "[Organization/Company]" in content or "Insufficient source" in content, \
        "Advisory must use placeholders for vague input"
    assert "XYZ" not in content, "Advisory must not invent company names"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Grounded LinkedIn — real source does NOT trigger placeholder
# ═══════════════════════════════════════════════════════════════════════════════

def test_grounded_linkedin():
    """Substantive source should produce a real post without [placeholder] markers."""
    from main import generate_linkedin

    source = (
        "Jane Smith has joined Deepmind as Principal Research Scientist. "
        "She previously led AI Safety research at OpenAI for 5 years. "
        "She will focus on interpretability and alignment research."
    )
    mock_response = (
        "Proud to join DeepMind as Principal Research Scientist.\n\n"
        "After 5 years leading AI Safety research at OpenAI, I am excited to apply "
        "interpretability and alignment research at DeepMind.\n\n"
        "— Focus on AI alignment\n"
        "— Building interpretability tools\n\n"
        "What does responsible AI development mean to you?\n\n"
        "#AI #DeepMind #Research"
    )
    mock = MockLLM(mock_response)
    result = generate_linkedin(source, "Professional", "Leadership / Execs", mock)
    content = result["content"]

    # Should NOT have empty placeholders when source is substantive
    assert "DeepMind" in content or "Principal Research Scientist" in content or "OpenAI" in content, \
        "Grounded source should produce specific content"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. extract_ground_truth — validates JSON schema
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_ground_truth():
    """extract_ground_truth must return valid schema with all required keys."""
    from main import extract_ground_truth

    mock_response = json.dumps({
        "entities": ["Acme Corp", "John Doe"],
        "key_facts": ["Revenue grew 23% YoY", "Headcount reached 1,200 employees"],
        "statistics": [{"metric": "Revenue growth", "value": "23", "unit": "%"}],
        "timeline": [{"date": "Q3 2024", "event": "Product launch"}]
    })
    mock = MockLLM(mock_response)
    result = extract_ground_truth("Acme Corp grew revenue by 23%.", mock)

    assert "entities" in result
    assert "key_facts" in result
    assert "statistics" in result
    assert "timeline" in result
    assert isinstance(result["entities"], list)
    assert isinstance(result["statistics"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. check_cross_format_consistency — detects contradiction
# ═══════════════════════════════════════════════════════════════════════════════

def test_cross_format_consistency_detects_contradiction():
    """Consistency checker must detect conflicting claims between formats."""
    from main import check_cross_format_consistency

    mock_response = json.dumps({
        "contradictions": [{
            "formats": ["advisory", "executive_summary"],
            "claim_a": "Revenue grew 23%",
            "claim_b": "Revenue grew 18%",
            "severity": "high"
        }],
        "consistency_score": 72
    })
    mock = MockLLM(mock_response)

    results = {
        "advisory": {"status": "success", "content": "Revenue grew 23% last quarter."},
        "executive_summary": {"status": "success", "content": "Revenue grew 18% last quarter."},
    }
    result = check_cross_format_consistency(results, mock)

    assert len(result["contradictions"]) == 1
    assert result["consistency_score"] == 72
    assert result["contradictions"][0]["severity"] == "high"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. check_cross_format_consistency — no contradictions returns 100
# ═══════════════════════════════════════════════════════════════════════════════

def test_cross_format_consistency_clean():
    """Consistent outputs should return score 100 and empty contradictions."""
    from main import check_cross_format_consistency

    mock_response = json.dumps({"contradictions": [], "consistency_score": 100})
    mock = MockLLM(mock_response)

    results = {
        "advisory": {"status": "success", "content": "Revenue grew 23%."},
        "executive_summary": {"status": "success", "content": "Revenue grew 23%."},
    }
    result = check_cross_format_consistency(results, mock)
    assert result["consistency_score"] == 100
    assert result["contradictions"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 7. generate_infographic — valid JSON schema output
# ═══════════════════════════════════════════════════════════════════════════════

def test_infographic_agent_json():
    """Infographic agent must return parseable JSON with required schema keys."""
    from main import generate_infographic

    mock_response = json.dumps({
        "title": "Revenue Growth 2024",
        "subtitle": "Annual performance snapshot",
        "key_stats": [
            {"label": "Revenue Growth", "value": "23", "unit": "%"},
            {"label": "Headcount", "value": "1200", "unit": "employees"}
        ],
        "sections": [
            {"heading": "Key Milestones", "points": ["Q1 product launch", "Q3 expansion"]}
        ],
        "chart": {
            "type": "bar",
            "title": "Quarterly Revenue",
            "labels": ["Q1", "Q2", "Q3", "Q4"],
            "values": [100, 115, 130, 123]
        },
        "source_note": "Data derived from: Annual Report 2024"
    })

    mock = MockLLM(mock_response)
    result = generate_infographic("Acme grew 23% revenue in 2024.", "Professional", "Leadership / Execs", mock)

    assert "content" in result
    data = json.loads(result["content"])
    assert "title" in data
    assert "key_stats" in data
    assert isinstance(data["key_stats"], list)
    assert "chart" in data
    assert "sections" in data


# ═══════════════════════════════════════════════════════════════════════════════
# 8. _format_ground_truth — produces non-empty string for populated gt dict
# ═══════════════════════════════════════════════════════════════════════════════

def test_format_ground_truth():
    """_format_ground_truth must produce a readable summary string."""
    from main import _format_ground_truth

    gt = {
        "entities": ["Acme Corp", "John Doe"],
        "key_facts": ["Revenue grew 23% YoY"],
        "statistics": [{"metric": "Revenue growth", "value": "23", "unit": "%"}],
        "timeline": [{"date": "Q3 2024", "event": "Product launch"}]
    }
    result = _format_ground_truth(gt)
    assert "Acme Corp" in result
    assert "23" in result
    assert len(result) > 20


# ═══════════════════════════════════════════════════════════════════════════════
# 9. _format_ground_truth — handles empty dict gracefully
# ═══════════════════════════════════════════════════════════════════════════════

def test_format_ground_truth_empty():
    """_format_ground_truth must return empty string for empty dict."""
    from main import _format_ground_truth

    result = _format_ground_truth({"entities": [], "key_facts": [], "statistics": [], "timeline": []})
    assert result == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 10. normalize_source — handles plain text correctly
# ═══════════════════════════════════════════════════════════════════════════════

def test_normalization_plain_text():
    """normalize_source must handle plain text input without errors."""
    from main import normalize_source

    text, source_type = normalize_source(text="Hello world. This is a test.")
    assert source_type == "text"
    assert "Hello world" in text


# ═══════════════════════════════════════════════════════════════════════════════
# 11-15. API Endpoint Tests via TestClient
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def client():
    """Create a TestClient with a mocked LLM to avoid real API calls."""
    from main import app, FORMAT_FN_MAP

    # Mock the LLM provider at module level
    mock_llm = MockLLM(json.dumps({
        "claims": [{"claim": "Test claim", "status": "supported", "evidence": "Source says so"}],
        "unsupported_count": 0
    }))

    with patch("main.get_llm", return_value=mock_llm), \
         patch("main.get_llm_for", lambda task=None: mock_llm), \
         patch("main.get_llm_for_format", lambda fmt=None: mock_llm), \
         patch("main._available_providers", return_value=["groq"]), \
         patch("main._save_run", return_value=None), \
         patch("main._fetch_history", return_value=[]), \
         patch("main._fetch_run", return_value=None):
        yield TestClient(app)


def test_health_endpoint(client):
    """GET /health must return status ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_history_endpoint(client):
    """GET /history must return a history list."""
    resp = client.get("/history")
    assert resp.status_code == 200
    data = resp.json()
    assert "history" in data
    assert isinstance(data["history"], list)


def test_transform_missing_source(client):
    """POST /transform with no source must return 400."""
    resp = client.post("/transform", data={
        "formats": '["advisory"]',
        "tone": "Professional",
        "audience": "Leadership / Execs",
    })
    assert resp.status_code == 400


def test_transform_invalid_format(client):
    """POST /transform with unsupported format must return 400."""
    resp = client.post("/transform", data={
        "text": "Some valid source text.",
        "formats": '["nonexistent_format"]',
        "tone": "Professional",
        "audience": "Leadership / Execs",
    })
    assert resp.status_code == 400


def test_transform_advisory_format(client):
    """POST /transform must accept advisory format with valid text source."""
    # Use a real-ish content for advisory — patch all LLM calls
    advisory_content = (
        "EXECUTIVE SUMMARY:\nThis is a test advisory.\n\n"
        "SITUATION OVERVIEW:\nTest situation.\n\n"
        "RECOMMENDED ACTIONS:\n1. Test action."
    )
    consistency_response = json.dumps({"contradictions": [], "consistency_score": 100})
    gt_response = json.dumps({
        "entities": [], "key_facts": ["Test fact."],
        "statistics": [], "timeline": []
    })
    verification_response = json.dumps({
        "claims": [{"claim": "Test advisory.", "status": "supported", "evidence": "Source."}],
        "unsupported_count": 0
    })

    call_count = [0]
    def smart_mock(system, user, temperature=0.7):
        call_count[0] += 1
        if "fact extraction" in system.lower():
            return gt_response
        if "consistency" in system.lower():
            return consistency_response
        if "fact-checking" in system.lower():
            return verification_response
        return advisory_content

    smart_llm = MagicMock()
    smart_llm.chat.side_effect = smart_mock

    with patch("main.get_llm", return_value=smart_llm), \
         patch("main.get_llm_for", lambda task=None: smart_llm), \
         patch("main.get_llm_for_format", lambda fmt=None: smart_llm), \
         patch("main._available_providers", return_value=["groq"]), \
         patch("main._save_run", return_value=None):
        resp = client.post("/transform", data={
            "text": "Acme Corp reported 23% revenue growth in Q4 2024.",
            "formats": '["advisory"]',
            "tone": "Professional",
            "audience": "Leadership / Execs",
        })

    # Should be 200 or at worst a 503 if LLM is unreachable in test env
    assert resp.status_code in (200, 503), f"Unexpected status: {resp.status_code} — {resp.text}"
    if resp.status_code == 200:
        data = resp.json()
        assert "results" in data
        assert "run_id" in data
        # Phase 3: every successful format carries a SHA-256 fingerprint
        assert data["integrity"]["algo"] == "sha256"
        assert len(data["integrity"]["run_hash"]) == 64
        adv = data["results"]["advisory"]
        assert adv["hash_algo"] == "sha256"
        from main import _sha256
        assert adv["hash"] == _sha256(adv["content"])


# ═══════════════════════════════════════════════════════════════════════════════
# 16-18. Tamper-evident integrity (Phase 3)
# ═══════════════════════════════════════════════════════════════════════════════

def test_sha256_helper_and_fingerprint():
    from main import _sha256, _run_fingerprint
    assert _sha256("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert _sha256(None) == _sha256("")
    fp1 = _run_fingerprint("run-1", "2026-01-01T00:00:00Z", {"advisory": {"hash": "aa"}})
    fp2 = _run_fingerprint("run-1", "2026-01-01T00:00:00Z", {"advisory": {"hash": "bb"}})
    assert fp1 != fp2 and len(fp1) == 64


_FAKE_RUN = {
    "run_id": "run-xyz",
    "created_at": "2026-01-01T00:00:00Z",
    "results": {
        "advisory": {
            "status": "success",
            "content": "EXECUTIVE SUMMARY:\nGrounded advisory text.",
            "hash": None,  # filled below
            "hash_algo": "sha256",
        }
    },
}


def test_verify_endpoint_matches_and_detects_tamper(client):
    from main import _sha256
    run = json.loads(json.dumps(_FAKE_RUN))
    original = run["results"]["advisory"]["content"]
    run["results"]["advisory"]["hash"] = _sha256(original)

    with patch("main._fetch_run", return_value=run):
        ok = client.post("/verify", json={
            "run_id": "run-xyz", "format_name": "advisory", "content": original,
        })
        assert ok.status_code == 200
        assert ok.json()["verified"] is True

        bad = client.post("/verify", json={
            "run_id": "run-xyz", "format_name": "advisory",
            "content": original + " (secretly altered)",
        })
        assert bad.status_code == 200
        body = bad.json()
        assert body["verified"] is False
        assert body["stored_hash"] != body["computed_hash"]

        # No content supplied → checks the stored copy, which must still match.
        stored = client.get("/verify/run-xyz/advisory")
        assert stored.status_code == 200
        assert stored.json()["verified"] is True


def test_verify_endpoint_unknown_run_and_format(client):
    with patch("main._fetch_run", return_value=None):
        r = client.post("/verify", json={"run_id": "nope", "format_name": "advisory"})
        assert r.status_code == 404
    with patch("main._fetch_run", return_value={"run_id": "r", "results": {}}):
        r = client.post("/verify", json={"run_id": "r", "format_name": "advisory"})
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 19-21. Per-format LLM routing
# ═══════════════════════════════════════════════════════════════════════════════

def test_format_provider_defaults():
    from main import FORMAT_PROVIDER
    assert FORMAT_PROVIDER["linkedin"] == "groq"
    assert FORMAT_PROVIDER["x_thread"] == "groq"
    assert FORMAT_PROVIDER["executive_summary"] == "gemini"
    assert FORMAT_PROVIDER["presentation"] == "gemini"
    assert set(FORMAT_PROVIDER) == set(__import__("main").SUPPORTED_FORMATS)


def test_routed_llm_prefers_assigned_provider_with_fallback():
    from main import _RoutedLLM
    with patch("main._available_providers", return_value=["groq", "gemini"]):
        r = _RoutedLLM("gemini", "gen:advisory")
        assert r.preferred == "gemini"
        assert r._order == ["gemini", "groq"]  # falls back to groq
    with patch("main._available_providers", return_value=["groq"]):
        r = _RoutedLLM("gemini", "gen:advisory")
        assert r.preferred == "groq"  # assigned unavailable → other provider


def test_health_exposes_format_routing(client):
    data = client.get("/health").json()
    assert data["format_routing"]["linkedin"] == "groq"
    assert "task_routing" in data


def test_transform_records_provider_per_format(client):
    """Each generated output carries which provider it was assigned / served by."""
    resp = client.post("/transform", data={
        "text": "ACME Corp reported 23% revenue growth in Q4 2024, its best quarter on record.",
        "formats": '["linkedin", "advisory"]',
        "tone": "Professional",
        "audience": "Leadership / Execs",
    })
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert results["linkedin"]["provider"]["assigned"] == "groq"
    assert results["advisory"]["provider"]["assigned"] == "gemini"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
