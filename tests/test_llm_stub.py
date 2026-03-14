"""Tests for StubLLMClient."""
from backend.services.llm import StubLLMClient


def test_stub_llm_extract_job_json_basic():
    text = """Title: Senior Support Engineer\nCompany: Acme Corp\nLocation: Remote\nMust have: Python\nMust have: FastAPI\nNice to have: Playwright\nDo you automate workflows?"""
    client = StubLLMClient()
    extraction = client.extract_job_json(text)
    payload = extraction.to_json()

    assert "Senior Support Engineer" in payload
    assert "Acme Corp" in payload
    assert "Python" in payload
    assert "Playwright" in payload


def test_stub_extract_empty_text():
    stub = StubLLMClient()
    result = stub.extract_job_json("")
    assert result.title is None
    assert result.must_haves == []


def test_stub_extract_url_detection():
    stub = StubLLMClient()
    result = stub.extract_job_json("Apply at https://example.com/apply\nTitle: Dev")
    assert result.apply_url == "https://example.com/apply"


def test_stub_extract_screening_questions():
    stub = StubLLMClient()
    result = stub.extract_job_json("Do you have a work permit?\nAre you authorized to work?")
    assert len(result.screening_questions) == 2


def test_stub_tailor_produces_coverage():
    stub = StubLLMClient()
    jd = {"must_haves": ["python", "fastapi"], "nice_to_haves": ["aws"]}
    blocks = [
        {"id": 1, "text": "Expert in Python and FastAPI development"},
        {"id": 2, "text": "Cloud infrastructure with Docker"},
    ]
    result = stub.tailor_resume(jd, blocks)
    assert "resume_body_md" in result
    assert len(result["coverage_table"]) > 0

    # python should be covered by block 1
    python_coverage = next(c for c in result["coverage_table"] if c["keyword"] == "python")
    assert 1 in python_coverage["support_block_ids"]

    # aws should be uncovered
    assert "aws" in result["uncovered_keywords"]


def test_stub_tailor_empty_blocks():
    stub = StubLLMClient()
    jd = {"must_haves": ["python"]}
    result = stub.tailor_resume(jd, [])
    assert result["resume_body_md"] == ""
    assert result["uncovered_keywords"] == ["python"]


def test_stub_detect_sections_finds_headers():
    stub = StubLLMClient()
    text = "Summary\nI am a developer\n\nExperience\nWorked at Acme\n\nEducation\nBS CS"
    sections = stub.detect_sections(text)
    categories = [s["category"] for s in sections]
    assert "summary" in categories
    assert "experience" in categories
    assert "education" in categories


def test_stub_detect_sections_fallback():
    stub = StubLLMClient()
    sections = stub.detect_sections("Just some random text with no headers")
    assert len(sections) == 1
    assert sections[0]["category"] == "other"


def test_stub_parse_section_extracts_tags():
    stub = StubLLMClient()
    blocks = stub.parse_section(
        "Built REST APIs with Python and Docker on Linux",
        "experience",
        "Work Experience",
    )
    assert len(blocks) == 1
    assert "python" in blocks[0]["tags"]
    assert "docker" in blocks[0]["tags"]
    assert "rest" in blocks[0]["tags"]
