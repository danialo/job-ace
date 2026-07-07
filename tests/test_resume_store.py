"""Tests for ResumeStoreService — generated-resume persistence and versioning."""
from __future__ import annotations

import json

from backend.services.resume_store import ResumeStoreService


def _save(store, job, blocks, data=b"%PDF fake", fmt="pdf", template="classic", tailored=False):
    return store.save_generated(
        job_id=job.id,
        block_ids=[b.id for b in blocks],
        tailored=tailored,
        template=template,
        fmt=fmt,
        data=data,
    )


def test_save_generated_creates_row_and_file(db_session, sample_job, sample_blocks, patched_settings):
    store = ResumeStoreService(db_session)
    row = _save(store, sample_job, sample_blocks)

    assert row.version == 1
    assert row.job_posting_id == sample_job.id
    assert json.loads(row.block_ids_json) == [b.id for b in sample_blocks]
    assert row.pdf_path is not None and row.docx_path is None
    with open(row.pdf_path, "rb") as fh:
        assert fh.read() == b"%PDF fake"
    # assembled display text contains the block text
    assert sample_blocks[0].text in row.resume_text


def test_same_content_second_format_merges_into_version(db_session, sample_job, sample_blocks, patched_settings):
    store = ResumeStoreService(db_session)
    first = _save(store, sample_job, sample_blocks, fmt="pdf")
    second = _save(store, sample_job, sample_blocks, data=b"PK docx", fmt="docx")

    assert second.id == first.id
    assert second.version == 1
    assert second.pdf_path is not None and second.docx_path is not None


def test_content_change_creates_new_version(db_session, sample_job, sample_blocks, patched_settings):
    store = ResumeStoreService(db_session)
    v1 = _save(store, sample_job, sample_blocks)
    v2 = _save(store, sample_job, sample_blocks[:2])  # different block selection

    assert v2.id != v1.id
    assert v2.version == 2
    # old row untouched
    assert v1.pdf_path is not None
    assert json.loads(v1.block_ids_json) == [b.id for b in sample_blocks]


def test_resume_text_applies_overrides(db_session, sample_job, sample_blocks, patched_settings, tmp_path, monkeypatch):
    import backend.services.resume_store as rs

    overrides = {sample_blocks[0].id: "TAILORED SUMMARY TEXT"}
    monkeypatch.setattr(rs, "load_tailored_overrides", lambda db, job_id: overrides)

    store = ResumeStoreService(db_session)
    row = _save(store, sample_job, sample_blocks, tailored=True)

    assert "TAILORED SUMMARY TEXT" in row.resume_text
    assert sample_blocks[0].text not in row.resume_text
    assert json.loads(row.overrides_json) == {str(sample_blocks[0].id): "TAILORED SUMMARY TEXT"}


def test_list_versions_newest_first(db_session, sample_job, sample_blocks, patched_settings):
    store = ResumeStoreService(db_session)
    _save(store, sample_job, sample_blocks)
    _save(store, sample_job, sample_blocks[:2])

    versions = store.list_versions(sample_job.id)
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["block_count"] == 2
    assert versions[0]["has_pdf"] is True and versions[0]["has_docx"] is False


def test_get_version_detail_latest_and_specific(db_session, sample_job, sample_blocks, patched_settings):
    store = ResumeStoreService(db_session)
    _save(store, sample_job, sample_blocks)
    _save(store, sample_job, sample_blocks[:2])

    latest = store.get_version_detail(sample_job.id)
    assert latest["version"] == 2
    assert latest["block_ids"] == [b.id for b in sample_blocks[:2]]
    assert latest["missing_block_ids"] == []
    assert latest["resume_text"]

    v1 = store.get_version_detail(sample_job.id, version=1)
    assert v1["version"] == 1
    assert v1["block_count"] == 3


def test_get_version_detail_reports_deleted_blocks(db_session, sample_job, sample_blocks, patched_settings):
    store = ResumeStoreService(db_session)
    _save(store, sample_job, sample_blocks)

    deleted_id = sample_blocks[0].id
    db_session.delete(sample_blocks[0])
    db_session.flush()

    detail = store.get_version_detail(sample_job.id)
    assert deleted_id in detail["missing_block_ids"]
    assert deleted_id not in detail["block_ids"]
    # the text snapshot survives block deletion
    assert detail["resume_text"]


def test_detail_and_summary_none_when_no_resumes(db_session, sample_job, patched_settings):
    store = ResumeStoreService(db_session)
    assert store.get_version_detail(sample_job.id) is None
    assert store.latest_summary(sample_job.id) is None
