"""Tests for AnalysisService."""
import json
from pathlib import Path

from backend.browser.analyzer import BrowserCapture
from backend.models import models
from backend.services.analysis import AnalysisService


class DummyAnalyzer:
    def capture(self, url: str, *, wait_until: str = "networkidle", force_playwright: bool = False) -> BrowserCapture:
        html = """
        <html>
            <body>
                <h1>Senior Python Engineer</h1>
                <h2>Responsibilities</h2>
                <ul>
                    <li>Build robust APIs</li>
                    <li>Collaborate with cross-functional teams</li>
                </ul>
                <p>Must have experience with FastAPI and Playwright.</p>
            </body>
        </html>
        """
        text = "Senior Python Engineer\nResponsibilities\nBuild robust APIs\nCollaborate with cross-functional teams\nMust have experience with FastAPI and Playwright."
        return BrowserCapture(
            url=url,
            html=html,
            text=text,
            screenshot=None,
            metadata={"source": "dummy"},
        )

    def _html_to_text(self, html: str) -> str:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text("\n", strip=True)


def test_analysis_service_writes_artifacts(db_session, sample_job, patched_settings):
    service = AnalysisService(db_session, analyzer=DummyAnalyzer())
    result = service.run(sample_job.id, recapture=True)

    analysis_path = Path(result["analysis_path"])
    assert analysis_path.exists()
    payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert payload["bullet_count"] == 2
    assert "FastAPI" in payload.get("sample_text", "")
    assert result["sections"]["headings"][0] == "Senior Python Engineer"
    assert db_session.get(models.JobPosting, sample_job.id).analysis_json_path == str(analysis_path)


def test_analysis_service_missing_job_raises(db_session, patched_settings):
    service = AnalysisService(db_session, analyzer=DummyAnalyzer())
    import pytest
    with pytest.raises(ValueError, match="not found"):
        service.run(9999, recapture=True)


def test_analysis_extract_sections():
    html = "<html><h1>Title</h1><h2>Sub</h2><p>Paragraph</p><ul><li>Item 1</li><li>Item 2</li></ul></html>"
    sections = AnalysisService._extract_sections(html)
    assert sections["headings"] == ["Title", "Sub"]
    assert len(sections["bullets"]) == 2
    assert "Paragraph" in sections["paragraphs"]
