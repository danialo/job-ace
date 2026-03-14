"""Shared test fixtures for database isolation and common setup."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.session import Base
from backend.models import models  # noqa: F401 - ensure models are registered
from backend.services.llm import StubLLMClient


@pytest.fixture()
def test_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    """Yield an isolated database session that rolls back after each test."""
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = TestSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def stub_llm():
    """Return a StubLLMClient for tests that need an LLM without API calls."""
    return StubLLMClient()


@pytest.fixture()
def sample_company(db_session):
    """Insert and return a sample Company."""
    company = models.Company(name="TestCo")
    db_session.add(company)
    db_session.flush()
    return company


@pytest.fixture()
def sample_job(db_session, sample_company, tmp_path):
    """Insert and return a sample JobPosting with an Application."""
    job = models.JobPosting(
        company_id=sample_company.id,
        url="https://example.com/jobs/test",
        title="Test Engineer",
        location="Remote",
    )
    db_session.add(job)
    db_session.flush()

    app = models.Application(job_posting_id=job.id)
    db_session.add(app)
    db_session.flush()
    job.application = app

    return job


@pytest.fixture()
def sample_blocks(db_session):
    """Insert and return a few sample ResumeBlocks."""
    blocks = [
        models.ResumeBlock(category="summary", tags="python,fastapi", text="Experienced Python developer with FastAPI expertise."),
        models.ResumeBlock(category="experience", tags="python,aws", text="Built scalable APIs using Python and AWS Lambda.",
                          job_title="Senior Developer", company="Acme Corp", start_date="2020", end_date="Present"),
        models.ResumeBlock(category="education", tags="cs", text="BS in Computer Science from State University."),
    ]
    for b in blocks:
        db_session.add(b)
    db_session.flush()
    return blocks


@pytest.fixture()
def patched_settings(tmp_path):
    """Patch get_settings to use tmp_path as data_root."""
    from backend.config import get_settings, Settings

    get_settings.cache_clear()

    settings = Settings(
        data_root=tmp_path / "artifacts",
        database_url="sqlite:///:memory:",
        openai_api_key="",
        llm_extraction_model="gpt-4o-mini",
        llm_resume_parsing_model="gpt-4.1",
        llm_tailoring_model="gpt-4.1",
        llm_provider="stub",
    )
    (tmp_path / "artifacts").mkdir(exist_ok=True)

    with patch("backend.services.artifacts.settings", settings), \
         patch("backend.config.get_settings", return_value=settings):
        yield settings

    get_settings.cache_clear()
