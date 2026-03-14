"""Tests for PrefillPlanner."""
from pathlib import Path

from backend.models import models
from backend.services.prefill import PrefillPlanner


def test_prefill_plan_produces_apply_url(db_session, sample_job, patched_settings, tmp_path):
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("Sample resume", encoding="utf-8")
    sample_job.apply_url = "https://example.com/apply"
    sample_job.application.resume_artifact_path = str(resume_path)
    db_session.flush()

    planner = PrefillPlanner(db_session)
    plan = planner.build_plan(sample_job.id)

    assert plan["apply_url"] == "https://example.com/apply"
    assert plan["uploads"][0]["path"] == str(resume_path)
    assert Path(plan["artifact_dir"]).exists()


def test_prefill_plan_missing_job_raises(db_session, patched_settings):
    import pytest
    planner = PrefillPlanner(db_session)
    with pytest.raises(ValueError, match="not found"):
        planner.build_plan(9999)


def test_prefill_plan_uses_url_fallback(db_session, sample_job, patched_settings):
    sample_job.apply_url = None
    db_session.flush()

    planner = PrefillPlanner(db_session)
    plan = planner.build_plan(sample_job.id)

    assert plan["apply_url"] == sample_job.url


def test_prefill_plan_no_resume_gives_empty_uploads(db_session, sample_job, patched_settings):
    sample_job.application.resume_artifact_path = None
    db_session.flush()

    planner = PrefillPlanner(db_session)
    plan = planner.build_plan(sample_job.id)

    assert plan["uploads"] == []
