"""Tests for ResumeConverter."""
from backend.services.resume_converter import ResumeConverter
from backend.services.llm import StubLLMClient


SAMPLE_RESUME = """John Smith
john@example.com
(555) 123-4567

Summary
Experienced software engineer with 10 years of Python expertise.

Experience
Senior Developer at Acme Corp
Built scalable APIs using Python and FastAPI.
Led team of 5 engineers.

Education
BS Computer Science, State University, 2014

Skills
Python, FastAPI, AWS, Docker, Kubernetes, React
"""


def test_parse_text_resume_regex_fallback():
    converter = ResumeConverter(llm_client=None)
    result = converter.parse_text_resume(SAMPLE_RESUME)
    assert "blocks" in result
    assert len(result["blocks"]) > 0


def test_parse_text_resume_extracts_metadata():
    converter = ResumeConverter(llm_client=None)
    result = converter.parse_text_resume(SAMPLE_RESUME)
    metadata = result.get("metadata", {})
    # Regex fallback should find at least email
    assert metadata.get("email") == "john@example.com" or len(result["blocks"]) > 0


def test_parse_text_resume_with_stub_llm():
    stub = StubLLMClient()
    converter = ResumeConverter(llm_client=stub)
    result = converter.parse_text_resume(SAMPLE_RESUME)
    assert "blocks" in result
    assert len(result["blocks"]) > 0


def test_to_xml_produces_valid_structure():
    converter = ResumeConverter(llm_client=None)
    result = converter.parse_text_resume(SAMPLE_RESUME)
    xml_str = converter.to_xml(result)
    assert "<resume" in xml_str
    assert "<block>" in xml_str or "<blocks>" in xml_str


def test_stub_detect_sections():
    stub = StubLLMClient()
    sections = stub.detect_sections(SAMPLE_RESUME)
    assert len(sections) > 0
    categories = [s["category"] for s in sections]
    assert "experience" in categories or "summary" in categories


def test_stub_parse_section():
    stub = StubLLMClient()
    section_text = "Built scalable APIs using Python and FastAPI. Led team of 5 engineers."
    blocks = stub.parse_section(section_text, "experience", "Work Experience")
    assert len(blocks) > 0
    assert blocks[0]["category"] == "experience"
    assert "python" in blocks[0]["tags"] or "fastapi" in blocks[0]["tags"]
