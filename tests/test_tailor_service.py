"""Tests for TailorService."""
import json

import pytest

from backend.models import models
from backend.services.llm import StubLLMClient
from backend.services.tailor import TailorService


def _setup_jd(sample_job, patched_settings, tmp_path):
    """Write a JD JSON file and set the path on the job."""
    jd = {
        "title": "Test Engineer",
        "company": "TestCo",
        "must_haves": ["python", "testing"],
        "nice_to_haves": ["aws"],
    }
    jd_path = tmp_path / "jd.json"
    jd_path.write_text(json.dumps(jd), encoding="utf-8")
    sample_job.jd_json_path = str(jd_path)


def test_tailor_generates_resume(db_session, sample_job, sample_blocks, patched_settings, tmp_path):
    _setup_jd(sample_job, patched_settings, tmp_path)
    db_session.flush()

    svc = TailorService(db_session, llm=StubLLMClient())
    block_ids = [b.id for b in sample_blocks]
    result = svc.run(sample_job.id, block_ids, "v1")

    assert "resume_body_md" in result
    assert len(result["resume_body_md"]) > 0
    assert "coverage" in result


def test_tailor_missing_job_raises(db_session, patched_settings):
    svc = TailorService(db_session, llm=StubLLMClient())
    with pytest.raises(ValueError, match="not found"):
        svc.run(9999, [1], "v1")


def test_tailor_no_blocks_raises(db_session, sample_job, patched_settings, tmp_path):
    _setup_jd(sample_job, patched_settings, tmp_path)
    db_session.flush()

    svc = TailorService(db_session, llm=StubLLMClient())
    with pytest.raises(ValueError, match="No resume blocks"):
        svc.run(sample_job.id, [], "v1")


def test_tailor_missing_block_raises(db_session, sample_job, patched_settings, tmp_path):
    _setup_jd(sample_job, patched_settings, tmp_path)
    db_session.flush()

    svc = TailorService(db_session, llm=StubLLMClient())
    with pytest.raises(ValueError, match="missing"):
        svc.run(sample_job.id, [9999], "v1")


def test_tailor_writes_artifacts(db_session, sample_job, sample_blocks, patched_settings, tmp_path):
    _setup_jd(sample_job, patched_settings, tmp_path)
    db_session.flush()

    svc = TailorService(db_session, llm=StubLLMClient())
    block_ids = [b.id for b in sample_blocks]
    svc.run(sample_job.id, block_ids, "v1")

    artifacts = db_session.query(models.Artifact).filter_by(job_posting_id=sample_job.id).all()
    kinds = {a.kind for a in artifacts}
    assert "tailor_request" in kinds
    assert "tailor_response" in kinds


def test_tailor_coverage_table(db_session, sample_job, sample_blocks, patched_settings, tmp_path):
    _setup_jd(sample_job, patched_settings, tmp_path)
    db_session.flush()

    svc = TailorService(db_session, llm=StubLLMClient())
    block_ids = [b.id for b in sample_blocks]
    result = svc.run(sample_job.id, block_ids, "v1")

    # "python" should be covered (it's in block text)
    covered_keywords = [c["keyword"] for c in result["coverage"]]
    assert "python" in covered_keywords
