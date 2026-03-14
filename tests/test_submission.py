"""Tests for SubmissionLogger."""
import pytest

from backend.models import models
from backend.services.submission import SubmissionLogger


def test_log_submit_updates_status(db_session, sample_job, patched_settings):
    logger = SubmissionLogger(db_session)
    app = logger.log(sample_job.id, "CONF-123", "Confirmed!", None)
    assert app.status == "submitted"
    assert app.applied_at is not None
    assert app.confirmation_id == "CONF-123"
    assert app.confirmation_text == "Confirmed!"


def test_log_submit_missing_job_raises(db_session, patched_settings):
    logger = SubmissionLogger(db_session)
    with pytest.raises(ValueError, match="not found"):
        logger.log(9999, None, None, None)


def test_log_submit_no_application_raises(db_session, sample_company, patched_settings):
    # Create a job without an application
    job = models.JobPosting(company_id=sample_company.id, url="https://example.com/no-app")
    db_session.add(job)
    db_session.flush()

    logger = SubmissionLogger(db_session)
    with pytest.raises(ValueError, match="Application record missing"):
        logger.log(job.id, None, None, None)


def test_log_submit_with_screenshot(db_session, sample_job, patched_settings, tmp_path):
    screenshot = tmp_path / "proof.png"
    screenshot.write_bytes(b"\x89PNG fake screenshot data")

    logger = SubmissionLogger(db_session)
    app = logger.log(sample_job.id, None, None, str(screenshot))
    assert app.status == "submitted"
    # Verify artifact registered
    artifacts = db_session.query(models.Artifact).filter_by(kind="submit_proof").all()
    assert len(artifacts) == 1
