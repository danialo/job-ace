"""Tests for compliance checking."""
from backend.services.compliance import ComplianceResult, _build_whitelist, _tokenize, run_compliance


def test_tokenize_basic():
    tokens = _tokenize("Hello World! Python 3.11 C++")
    assert "hello" in tokens
    assert "world" in tokens
    assert "python" in tokens
    assert "c++" in tokens
    assert "3" in tokens


def test_tokenize_empty():
    assert _tokenize("") == []


def test_build_whitelist():
    blocks = [
        {"text": "Expert in Python and FastAPI"},
        {"text": "Built APIs with AWS Lambda"},
    ]
    whitelist = _build_whitelist(blocks)
    assert "python" in whitelist
    assert "fastapi" in whitelist
    assert "aws" in whitelist


def test_compliance_passes_when_all_tokens_from_blocks(db_session, sample_job, patched_settings):
    blocks = [{"text": "Python FastAPI developer"}]
    tailor_output = {
        "resume_body_md": "Python FastAPI developer",
        "resume_ats_text": "Python FastAPI developer",
    }
    result = run_compliance(db_session, sample_job, blocks, tailor_output)
    assert result.ok is True
    assert result.extraneous_tokens == []


def test_compliance_fails_with_extraneous_tokens(db_session, sample_job, patched_settings):
    blocks = [{"text": "Python developer"}]
    tailor_output = {
        "resume_body_md": "Python developer with Kubernetes expertise",
        "resume_ats_text": "Python developer with Kubernetes expertise",
    }
    result = run_compliance(db_session, sample_job, blocks, tailor_output)
    assert result.ok is False
    assert "kubernetes" in result.extraneous_tokens


def test_compliance_result_to_json():
    result = ComplianceResult(ok=True, extraneous_tokens=[], blocked=False, notes="all good")
    data = result.to_json()
    import json
    parsed = json.loads(data)
    assert parsed["ok"] is True
    assert parsed["notes"] == "all good"
