import json
from pathlib import Path

from backend.browser.analyzer import BrowserCapture
from backend.config import get_settings
from backend.db.session import get_session, init_db
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


def test_analysis_service_writes_artifacts(tmp_path):
    init_db()
    settings = get_settings()
    settings.data_root = tmp_path

    with get_session() as session:
        company = models.Company(name="SampleCo")
        session.add(company)
        session.flush()

        job_posting = models.JobPosting(
            company_id=company.id,
            url="https://example.com/jobs/python",
            title="Python Engineer",
            location="Remote",
        )
        session.add(job_posting)
        session.flush()

        service = AnalysisService(session, analyzer=DummyAnalyzer())
        result = service.run(job_posting.id, recapture=True)

        analysis_path = Path(result["analysis_path"])
        assert analysis_path.exists()
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert payload["bullet_count"] == 2
        assert "FastAPI" in payload.get("sample_text", "")
        assert result["sections"]["headings"][0] == "Senior Python Engineer"
        assert session.get(models.JobPosting, job_posting.id).analysis_json_path == str(analysis_path)
