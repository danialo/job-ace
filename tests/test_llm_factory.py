"""Tests for LLM client factory and AnthropicLLMClient."""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.services.llm import (
    AnthropicLLMClient,
    BaseLLMClient,
    JDExtraction,
    StubLLMClient,
    get_llm_client,
)


def test_get_llm_client_default_is_stub():
    """Without config, factory returns StubLLMClient."""
    with patch("backend.services.llm.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            llm_provider="stub",
            anthropic_api_key=None,
        )
        client = get_llm_client()
        assert isinstance(client, StubLLMClient)


def test_get_llm_client_anthropic_without_key_falls_back():
    """Anthropic provider without API key falls back to stub."""
    with patch("backend.services.llm.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            llm_provider="anthropic",
            anthropic_api_key=None,
        )
        client = get_llm_client()
        assert isinstance(client, StubLLMClient)


def test_get_llm_client_anthropic_with_key():
    """Anthropic provider with API key returns AnthropicLLMClient."""
    with patch("backend.services.llm.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            llm_provider="anthropic",
            anthropic_api_key="sk-ant-test-key",
            anthropic_model="claude-sonnet-4-20250514",
            llm_max_tokens=4096,
            llm_temperature=0.3,
        )
        client = get_llm_client()
        assert isinstance(client, AnthropicLLMClient)


def test_jd_extraction_from_dict():
    """JDExtraction.from_dict parses correctly."""
    data = {
        "title": "Software Engineer",
        "company": "Test Corp",
        "location": "Remote",
        "employment_type": "full-time",
        "seniority": "senior",
        "salary_range": {"min": 100000, "max": 150000, "currency": "USD"},
        "must_haves": ["Python", "FastAPI"],
        "nice_to_haves": ["Kubernetes"],
        "screening_questions": ["Why this role?"],
        "apply_url": "https://example.com/apply",
        "deadline": "2026-04-01",
        "portal_hint": "greenhouse",
    }
    extraction = JDExtraction.from_dict(data)
    assert extraction.title == "Software Engineer"
    assert extraction.company == "Test Corp"
    assert extraction.salary_min == 100000
    assert extraction.salary_max == 150000
    assert extraction.must_haves == ["Python", "FastAPI"]


def test_anthropic_client_parse_json_response():
    """AnthropicLLMClient can parse JSON from markdown blocks."""
    client = AnthropicLLMClient(api_key="test")
    
    # Plain JSON
    result = client._parse_json_response('{"title": "Engineer"}')
    assert result["title"] == "Engineer"
    
    # JSON in code block
    result = client._parse_json_response('```json\n{"title": "Dev"}\n```')
    assert result["title"] == "Dev"
    
    # JSON in plain code block
    result = client._parse_json_response('```\n{"title": "SRE"}\n```')
    assert result["title"] == "SRE"


def test_anthropic_client_fallback_on_error():
    """AnthropicLLMClient falls back to stub on API error."""
    client = AnthropicLLMClient(api_key="invalid-key")
    
    # This will fail because the key is invalid, and should fall back to stub
    text = "Title: Test Job\nCompany: Test Co\nMust have: Testing"
    extraction = client.extract_job_json(text)
    
    # Should get a result (from stub fallback)
    assert extraction.title is not None


def test_base_llm_client_is_abstract():
    """BaseLLMClient cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseLLMClient()
