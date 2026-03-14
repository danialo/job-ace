"""Tests for IntakeService."""
import pytest
from unittest.mock import patch

from backend.models import models
from backend.services.intake import IntakeService
from backend.services.llm import StubLLMClient


SAMPLE_HTML = """
<html><body>
<h1>Title: Senior Python Engineer</h1>
<p>Company: Acme Corp</p>
<p>Location: Remote</p>
<p>Must have Python experience</p>
<p>Nice to have AWS skills</p>
<p>Do you have a work permit?</p>
<a href="https://acme.com/apply">Apply Here</a>
</body></html>
"""


def _make_service(db_session, patched_settings):
    """Create an IntakeService with mocked fetch and stub LLM."""
    svc = IntakeService(db_session, llm=StubLLMClient())
    return svc


def test_intake_creates_job_and_company(db_session, patched_settings):
    svc = _make_service(db_session, patched_settings)
    with patch.object(svc, "_fetch_html", return_value=SAMPLE_HTML):
        job = svc.run("https://acme.com/jobs/123")

    assert job.id is not None
    assert job.status == "intake"
    assert job.company.name is not None


def test_intake_existing_url_returns_existing(db_session, sample_company, patched_settings):
    # Pre-create a job
    existing = models.JobPosting(company_id=sample_company.id, url="https://example.com/dupe")
    db_session.add(existing)
    db_session.flush()

    svc = _make_service(db_session, patched_settings)
    result = svc.run("https://example.com/dupe")
    assert result.id == existing.id


def test_intake_force_recaptures(db_session, sample_company, patched_settings):
    existing = models.JobPosting(company_id=sample_company.id, url="https://example.com/force")
    db_session.add(existing)
    db_session.flush()

    svc = _make_service(db_session, patched_settings)
    with patch.object(svc, "_fetch_html", return_value=SAMPLE_HTML):
        result = svc.run("https://example.com/force", force=True)
    assert result.id == existing.id
    assert result.status == "intake"


def test_intake_extracts_fields_via_stub(db_session, patched_settings):
    svc = _make_service(db_session, patched_settings)
    with patch.object(svc, "_fetch_html", return_value=SAMPLE_HTML):
        job = svc.run("https://acme.com/jobs/456")

    assert job.title is not None
    assert job.jd_json_path is not None


def test_intake_writes_artifacts(db_session, patched_settings):
    svc = _make_service(db_session, patched_settings)
    with patch.object(svc, "_fetch_html", return_value=SAMPLE_HTML):
        job = svc.run("https://acme.com/jobs/789")

    assert job.captured_html_path is not None
    assert job.jd_json_path is not None
    artifacts = db_session.query(models.Artifact).filter_by(job_posting_id=job.id).all()
    assert len(artifacts) >= 3  # html, text, jd_json at minimum


def test_intake_creates_application(db_session, patched_settings):
    svc = _make_service(db_session, patched_settings)
    with patch.object(svc, "_fetch_html", return_value=SAMPLE_HTML):
        job = svc.run("https://acme.com/jobs/app-test")

    assert job.application is not None
    assert job.application.status == "draft"


def test_guess_company_from_url():
    assert IntakeService._guess_company_from_url("https://www.acme.com/jobs") == "Acme"
    assert IntakeService._guess_company_from_url("https://careers.bigco.io/apply") == "Bigco"
