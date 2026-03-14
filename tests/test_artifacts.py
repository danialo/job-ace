"""Tests for ArtifactManager."""
from backend.models import models
from backend.services.artifacts import ArtifactManager


def test_ensure_job_dir_creates_subdirectories(db_session, sample_job, patched_settings):
    mgr = ArtifactManager(db_session)
    job_dir = mgr.ensure_job_dir(sample_job)
    assert (job_dir / "raw").is_dir()
    assert (job_dir / "derived").is_dir()
    assert (job_dir / "submission").is_dir()


def test_ensure_job_dir_naming_convention(db_session, sample_job, patched_settings):
    mgr = ArtifactManager(db_session)
    job_dir = mgr.ensure_job_dir(sample_job)
    name = job_dir.name
    assert "testco" in name
    assert "test-engineer" in name
    assert f"job{sample_job.id}" in name


def test_write_text_creates_file(db_session, sample_job, patched_settings):
    mgr = ArtifactManager(db_session)
    path = mgr.write_text(sample_job, "test_kind", "raw/test.txt", "hello world")
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "hello world"


def test_write_text_registers_artifact(db_session, sample_job, patched_settings):
    mgr = ArtifactManager(db_session)
    mgr.write_text(sample_job, "test_kind", "raw/test.txt", "hello")
    artifacts = db_session.query(models.Artifact).filter_by(kind="test_kind").all()
    assert len(artifacts) == 1
    assert artifacts[0].sha256 is not None
    assert artifacts[0].size_bytes > 0


def test_write_bytes_creates_file(db_session, sample_job, patched_settings):
    mgr = ArtifactManager(db_session)
    path = mgr.write_bytes(sample_job, "bin_kind", "raw/test.bin", b"\x00\x01\x02")
    assert path.exists()
    assert path.read_bytes() == b"\x00\x01\x02"


def test_register_path_deduplication(db_session, sample_job, patched_settings):
    mgr = ArtifactManager(db_session)
    mgr.write_text(sample_job, "dup_kind", "raw/dup.txt", "version 1")
    mgr.write_text(sample_job, "dup_kind", "raw/dup.txt", "version 2")
    artifacts = db_session.query(models.Artifact).filter_by(kind="dup_kind").all()
    assert len(artifacts) == 1
    assert artifacts[0].size_bytes == len("version 2")


def test_get_artifact(db_session, sample_job, patched_settings):
    mgr = ArtifactManager(db_session)
    mgr.write_text(sample_job, "findme", "raw/findme.txt", "found")
    artifact = mgr.get_artifact(sample_job, "findme")
    assert artifact is not None
    assert artifact.kind == "findme"


def test_get_artifact_missing(db_session, sample_job, patched_settings):
    mgr = ArtifactManager(db_session)
    assert mgr.get_artifact(sample_job, "nonexistent") is None
