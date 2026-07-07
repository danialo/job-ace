"""Tests for SQLAlchemy models."""
import pytest
from sqlalchemy.exc import IntegrityError

from backend.models import models


def test_company_unique_name(db_session):
    db_session.add(models.Company(name="Acme"))
    db_session.flush()
    db_session.add(models.Company(name="Acme"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_job_posting_defaults(db_session, sample_company):
    job = models.JobPosting(company_id=sample_company.id, url="https://example.com/j")
    db_session.add(job)
    db_session.flush()
    assert job.status == "intake"
    assert job.created_at is not None


def test_application_defaults(db_session, sample_job):
    assert sample_job.application.status == "draft"
    assert sample_job.application.created_at is not None


def test_resume_block_defaults(db_session):
    block = models.ResumeBlock(text="Hello world")
    db_session.add(block)
    db_session.flush()
    assert block.version == 1
    assert block.id is not None


def test_company_to_job_relationship(db_session, sample_company, sample_job):
    assert sample_job in sample_company.job_postings


def test_job_to_application_relationship(db_session, sample_job):
    assert sample_job.application is not None
    assert sample_job.application.job_posting is sample_job


def test_artifact_creation(db_session, sample_job):
    artifact = models.Artifact(
        job_posting_id=sample_job.id,
        kind="test_kind",
        path="/tmp/test.txt",
        sha256="abc123",
    )
    db_session.add(artifact)
    db_session.flush()
    assert artifact.id is not None
    assert artifact in sample_job.artifacts


def test_resume_block_usage(db_session, sample_job, sample_blocks):
    usage = models.ResumeBlockUsage(
        application_id=sample_job.application.id,
        resume_block_id=sample_blocks[0].id,
        used_in="body",
    )
    db_session.add(usage)
    db_session.flush()
    assert usage in sample_job.application.block_usage


def test_generated_resume_roundtrip(db_session, sample_job):
    row = models.GeneratedResume(
        job_posting_id=sample_job.id,
        version=1,
        block_ids_json="[1, 2]",
        overrides_json="{}",
        tailored=False,
        template="classic",
        resume_text="Some resume text",
        content_sha="abc123",
    )
    db_session.add(row)
    db_session.flush()

    assert row.id is not None
    assert row.pdf_path is None
    assert sample_job.generated_resumes == [row]


def test_generated_resume_version_unique_per_job(db_session, sample_job):
    import pytest as _pytest
    from sqlalchemy.exc import IntegrityError

    for _ in range(2):
        db_session.add(models.GeneratedResume(
            job_posting_id=sample_job.id, version=1, block_ids_json="[]",
            overrides_json="{}", tailored=False, template="classic",
            resume_text="", content_sha="x",
        ))
    with _pytest.raises(IntegrityError):
        db_session.flush()


def test_uploaded_resume_roundtrip(db_session):
    row = models.UploadedResume(
        filename="resume.pdf", path="/tmp/resumes/abc_resume.pdf",
        sha256="deadbeef", size_bytes=1234,
    )
    db_session.add(row)
    db_session.flush()
    assert row.id is not None
    assert row.block_ids_json is None
