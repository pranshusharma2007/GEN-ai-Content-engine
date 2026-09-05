"""
Unit and integration tests for insufficient-source and vague-input handling.
SIH26154 · Team WildCard
"""

import os
import re
import unittest
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend directory is in path and env is loaded
backend_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=backend_dir.parent.parent / ".env")
load_dotenv(dotenv_path=backend_dir / ".env")

from main import (
    LLMProvider,
    generate_linkedin,
    generate_advisory,
    generate_executive_summary,
    generate_x_thread,
    generate_presentation,
    verify_claims,
    get_llm,
)


class MockLLM(LLMProvider):
    """Deterministic mock provider for unit testing prompts and responses."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_system = ""
        self.last_user = ""

    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        self.last_system = system
        self.last_user = user
        return self.response_text


class TestVagueInputHandling(unittest.TestCase):
    """Tests verifying behavior when source text is vague or insufficient."""

    def test_prompt_contains_anti_hallucination_and_placeholder_instructions(self):
        """Verify that all generation agents instruct the model to use placeholders for vague inputs."""
        mock = MockLLM("Template response")
        vague_source = "give company joining post"

        generate_linkedin(vague_source, "Professional", "General Public", mock)
        self.assertIn("STRICT GROUNDING", mock.last_system)
        self.assertIn("INSUFFICIENT OR VAGUE SOURCE", mock.last_system)
        self.assertIn("[Company Name]", mock.last_system)

        generate_advisory(vague_source, "Professional", "Leadership / Execs", mock)
        self.assertIn("STRICT GROUNDING", mock.last_system)
        self.assertIn("placeholders", mock.last_system)

        generate_executive_summary(vague_source, "Professional", "Leadership / Execs", mock)
        self.assertIn("STRICT GROUNDING", mock.last_system)
        self.assertIn("placeholders", mock.last_system)

        generate_x_thread(vague_source, "Professional", "General Public", mock)
        self.assertIn("STRICT GROUNDING", mock.last_system)
        self.assertIn("placeholders", mock.last_system)

        generate_presentation(vague_source, "Professional", "General Public", mock)
        self.assertIn("STRICT GROUNDING", mock.last_system)
        self.assertIn("placeholders", mock.last_system)

    def test_verifier_system_rules_exclude_placeholders(self):
        """Verify the verifier system prompt explicitly treats bracketed placeholders as non-claims."""
        from main import _VERIFIER_SYSTEM
        self.assertIn("Placeholders in square brackets", _VERIFIER_SYSTEM)
        self.assertIn("[Company Name]", _VERIFIER_SYSTEM)
        self.assertIn("unsupported", _VERIFIER_SYSTEM)

    def test_verifier_flags_hallucinated_entities(self):
        """Verify the claim verifier flags fabricated entities not in source."""
        source = "give company joining post"
        hallucinated_post = (
            "I am excited to join XYZ Corporation as Vice President of Global Strategy "
            "leveraging my 15 years of Fortune 500 leadership."
        )

        mock_verifier_response = (
            '{"claims": ['
            '{"claim": "Joined XYZ Corporation as Vice President", "status": "unsupported", "reason": "Not in source"},'
            '{"claim": "15 years of Fortune 500 leadership", "status": "unsupported", "reason": "Not in source"}'
            '], "unsupported_count": 2}'
        )
        mock = MockLLM(mock_verifier_response)
        result = verify_claims(source, hallucinated_post, mock)
        self.assertEqual(result.get("unsupported_count"), 2)
        self.assertTrue(any(c["status"] == "unsupported" for c in result["claims"]))

    def test_verifier_accepts_clean_template_output(self):
        """Verify the claim verifier passes clean placeholder templates with zero unsupported claims."""
        source = "give company joining post"
        clean_template = (
            "I am thrilled to announce that I have joined [Company Name] as [Job Title / Role]. "
            "In this role, I will be responsible for [Key Responsibility] and driving [Key Goal/Achievement]."
        )

        mock_verifier_response = '{"claims": [], "unsupported_count": 0}'
        mock = MockLLM(mock_verifier_response)
        result = verify_claims(source, clean_template, mock)
        self.assertEqual(result.get("unsupported_count"), 0)
        self.assertEqual(len(result.get("claims", [])), 0)

    def test_live_groq_vague_input_handling(self):
        """Live integration test with Groq (skipped if GROQ_API_KEY is not configured)."""
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            self.skipTest("GROQ_API_KEY not configured; skipping live test.")

        try:
            llm = get_llm()
            vague_source = "give company joining post"
            result = generate_linkedin(vague_source, "Professional", "General Public", llm)
            content = result.get("content", "")

            # Verify it did not invent a fictional company like 'XYZ Corporation'
            self.assertNotIn("XYZ Corporation", content)
            self.assertNotIn("Acme Corp", content)

            # Verify it returned either bracketed placeholders or an insufficient source notice
            has_placeholders = bool(re.search(r"\[[A-Za-z\s\/\-_]+\]", content))
            has_insufficient_notice = "insufficient" in content.lower()
            self.assertTrue(
                has_placeholders or has_insufficient_notice,
                f"Generated content should contain placeholders or insufficient notice. Got:\n{content}",
            )
        except Exception as exc:
            # If rate limited by provider, skip rather than hard fail CI
            if "429" in str(exc) or "rate_limit" in str(exc).lower():
                self.skipTest(f"Groq rate limited (429): {exc}")
            else:
                raise


if __name__ == "__main__":
    unittest.main()
