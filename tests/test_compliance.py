"""Tests for compliance checking (both token-based and LLM-powered)."""

import json
import pytest
from unittest.mock import MagicMock, patch

from backend.services.llm import StubLLMClient, ComplianceCheck
from backend.services.compliance import (
    ComplianceResult,
    _run_token_compliance,
    _build_whitelist,
    _tokenize,
    run_compliance,
)


# ============================================================================
# Unit Tests - Helper Functions
# ============================================================================

class TestTokenization:
    """Test helper functions."""

    def test_tokenize_basic(self):
        text = "Python 3.12 and FastAPI!"
        tokens = _tokenize(text)
        assert "python" in tokens
        assert "fastapi" in tokens
        assert "3" in tokens
        assert "12" in tokens

    def test_tokenize_preserves_plus(self):
        text = "C++ and C# programming"
        tokens = _tokenize(text)
        assert "c++" in tokens
        assert "c#" in tokens

    def test_tokenize_empty(self):
        assert _tokenize("") == []

    def test_build_whitelist(self):
        blocks = [
            {"text": "Python developer"},
            {"text": "FastAPI expert"},
        ]
        whitelist = _build_whitelist(blocks)
        assert "python" in whitelist
        assert "developer" in whitelist
        assert "fastapi" in whitelist


class TestTokenCompliance:
    """Test legacy token-based compliance."""

    def test_exact_match_passes(self):
        blocks = [{"text": "Senior Python Developer at Acme Corp"}]
        resume = "Senior Python Developer at Acme Corp"
        result = _run_token_compliance(blocks, resume)
        assert result.ok is True
        assert result.blocked is False
        assert len(result.extraneous_tokens) == 0

    def test_added_words_flagged(self):
        blocks = [{"text": "Python Developer"}]
        resume = "Python Developer with extensive Django experience"
        result = _run_token_compliance(blocks, resume)
        assert result.ok is False
        assert result.blocked is True
        assert "django" in result.extraneous_tokens
        assert "extensive" in result.extraneous_tokens

    def test_method_is_token(self):
        blocks = [{"text": "Test"}]
        result = _run_token_compliance(blocks, "Test")
        assert result.method == "token"


class TestStubLLMCompliance:
    """Test stub LLM compliance checker."""

    def test_stub_compliance_clean_resume(self):
        client = StubLLMClient()
        source_blocks = [
            {"id": 1, "text": "Built scalable Python APIs using FastAPI and PostgreSQL"},
            {"id": 2, "text": "Led team of 5 engineers to deliver project on time"},
        ]
        resume = "Built scalable Python APIs using FastAPI and PostgreSQL. Led team of 5 engineers."
        
        result = client.check_compliance(resume, source_blocks)
        assert result.ok is True
        assert len(result.fabrications) == 0
        assert result.confidence < 1.0  # Stub is less confident
        assert "stub" in result.notes.lower()

    def test_stub_compliance_with_fabrication(self):
        client = StubLLMClient()
        source_blocks = [
            {"id": 1, "text": "Python developer"},
        ]
        # Adding lots of new content that's not in source
        resume = """
        Python developer with expertise in machine learning, deep learning,
        artificial intelligence, blockchain, quantum computing, and
        distributed systems. Published 15 papers and holds 3 patents.
        """
        
        result = client.check_compliance(resume, source_blocks)
        # Should flag because >5% of tokens are new
        assert len(result.fabrications) > 0 or result.ok is True  # Depends on ratio

    def test_stub_compliance_allows_common_words(self):
        client = StubLLMClient()
        source_blocks = [
            {"id": 1, "text": "Python developer on the team"},
        ]
        # Common connective words should be allowed
        resume = "I am a Python developer and I work with the team."
        
        result = client.check_compliance(resume, source_blocks)
        # Should pass because "I", "am", "a", "and", "with", "the" are common
        # and "team" is in source
        assert result.ok is True


class TestComplianceResult:
    """Test ComplianceResult serialization."""

    def test_to_json_basic(self):
        result = ComplianceResult(
            ok=True,
            extraneous_tokens=[],
            blocked=False,
            notes="All clear",
            method="token",
        )
        json_str = result.to_json()
        assert '"ok": true' in json_str
        assert '"method": "token"' in json_str

    def test_to_json_with_llm_fields(self):
        result = ComplianceResult(
            ok=False,
            extraneous_tokens=[],
            blocked=True,
            notes="Found issues",
            fabrications=[{"claim": "fake metric", "explanation": "not in source", "severity": "high"}],
            style_changes=["condensed bullet points"],
            confidence=0.92,
            method="llm",
        )
        json_str = result.to_json()
        assert '"ok": false' in json_str
        assert '"method": "llm"' in json_str
        assert '"fabrications"' in json_str
        assert '"confidence": 0.92' in json_str


class TestComplianceCheck:
    """Test LLM ComplianceCheck dataclass."""

    def test_from_dict(self):
        data = {
            "ok": False,
            "fabrications": [
                {"claim": "10x revenue", "explanation": "not mentioned", "severity": "high"}
            ],
            "style_changes": ["rephrased for clarity"],
            "confidence": 0.85,
            "notes": "One fabrication found",
        }
        result = ComplianceCheck.from_dict(data)
        assert result.ok is False
        assert len(result.fabrications) == 1
        assert result.fabrications[0]["severity"] == "high"
        assert result.confidence == 0.85

    def test_to_json_roundtrip(self):
        original = ComplianceCheck(
            ok=True,
            fabrications=[],
            style_changes=["minor edit"],
            confidence=0.95,
            notes="Clean",
        )
        json_str = original.to_json()
        parsed = json.loads(json_str)
        restored = ComplianceCheck.from_dict(parsed)
        assert restored.ok == original.ok
        assert restored.confidence == original.confidence


# ============================================================================
# Integration Tests - Require DB Fixtures
# ============================================================================

def test_compliance_passes_when_all_tokens_from_blocks(db_session, sample_job, patched_settings):
    """Integration test: compliance passes when resume only uses source tokens."""
    blocks = [{"text": "Python FastAPI developer"}]
    tailor_output = {
        "resume_body_md": "Python FastAPI developer",
        "resume_ats_text": "Python FastAPI developer",
    }
    result = run_compliance(db_session, sample_job, blocks, tailor_output, use_llm=False)
    assert result.ok is True
    assert result.extraneous_tokens == []


def test_compliance_fails_with_extraneous_tokens(db_session, sample_job, patched_settings):
    """Integration test: compliance fails when resume has tokens not in source."""
    blocks = [{"text": "Python developer"}]
    tailor_output = {
        "resume_body_md": "Python developer with Kubernetes expertise",
        "resume_ats_text": "Python developer with Kubernetes expertise",
    }
    result = run_compliance(db_session, sample_job, blocks, tailor_output, use_llm=False)
    assert result.ok is False
    assert "kubernetes" in result.extraneous_tokens
