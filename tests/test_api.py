"""Tests for FastAPI API endpoints."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.app import app
from backend.db.session import Base, get_db
from backend.models import models


# --- Test database setup ---

_test_engine = None
_TestSessionLocal = None


@pytest.fixture(autouse=True)
def _setup_test_db():
    """Create a fresh in-memory DB for each test, override get_db globally."""
    global _test_engine, _TestSessionLocal

    _test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=_test_engine)
    _TestSessionLocal = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False)

    def override_get_db():
        session = _TestSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_test_engine)
    _test_engine.dispose()


@pytest.fixture()
def api_session():
    """Return a session on the same test engine for direct data setup."""
    session = _TestSessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client():
    with patch("backend.api.app.init_db"):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# --- List endpoints (empty state) ---

def test_list_jobs_empty(client):
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_blocks_empty(client):
    resp = client.get("/blocks")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_applications_empty(client):
    resp = client.get("/applications")
    assert resp.status_code == 200
    assert resp.json() == []


# --- Block CRUD ---

def test_confirm_and_list_blocks(client):
    payload = {
        "blocks": [
            {"category": "summary", "tags": ["python"], "content": "Expert Python dev"},
            {"category": "experience", "tags": ["aws"], "content": "Built cloud infra"},
        ]
    }
    resp = client.post("/confirm-resume-blocks", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["blocks_saved"] == 2
    assert len(data["block_ids"]) == 2

    # Now list them
    resp = client.get("/blocks")
    assert resp.status_code == 200
    blocks = resp.json()
    assert len(blocks) == 2


def test_update_block(client):
    # Create a block first
    client.post("/confirm-resume-blocks", json={
        "blocks": [{"category": "summary", "tags": [], "content": "Original text"}]
    })

    resp = client.put("/blocks/1", json={"text": "Updated text"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "Updated text"


def test_update_block_not_found(client):
    resp = client.put("/blocks/9999", json={"text": "nope"})
    assert resp.status_code == 404


def test_delete_block(client):
    client.post("/confirm-resume-blocks", json={
        "blocks": [{"category": "skills", "tags": [], "content": "Python"}]
    })
    resp = client.delete("/blocks/1")
    assert resp.status_code == 200

    # Verify gone
    resp = client.get("/blocks")
    assert len(resp.json()) == 0


def test_delete_block_not_found(client):
    resp = client.delete("/blocks/9999")
    assert resp.status_code == 404


def test_delete_all_blocks(client):
    client.post("/confirm-resume-blocks", json={
        "blocks": [
            {"category": "a", "tags": [], "content": "one"},
            {"category": "b", "tags": [], "content": "two"},
        ]
    })
    resp = client.delete("/blocks")
    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 2


def test_confirm_empty_blocks_returns_400(client):
    resp = client.post("/confirm-resume-blocks", json={"blocks": []})
    assert resp.status_code == 400


# --- Jobs and intake ---

def test_list_jobs_with_data(client, api_session):
    company = models.Company(name="APICo")
    api_session.add(company)
    api_session.flush()
    job = models.JobPosting(company_id=company.id, url="https://example.com/j", title="Dev")
    api_session.add(job)
    api_session.flush()

    resp = client.get("/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Dev"


# --- Job detail (review capture) ---

def test_get_job_detail(client, api_session):
    company = models.Company(name="DetailCo")
    api_session.add(company)
    api_session.flush()
    job = models.JobPosting(
        company_id=company.id,
        url="paste:abc123",
        title="Advocate",
        location="Remote",
        must_haves_json=json.dumps(["Degree in social work", "1-3 years experience"]),
        nice_to_haves_json=json.dumps(["Bilingual"]),
        screening_questions_json=json.dumps(["Why this role?"]),
    )
    api_session.add(job)
    api_session.flush()

    resp = client.get(f"/jobs/{job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job.id
    assert data["title"] == "Advocate"
    assert data["company"] == "DetailCo"
    assert data["url"] == "paste:abc123"
    assert data["must_haves"] == ["Degree in social work", "1-3 years experience"]
    assert data["nice_to_haves"] == ["Bilingual"]
    assert data["screening_questions"] == ["Why this role?"]


def test_get_job_detail_empty_requirements(client, api_session):
    company = models.Company(name="EmptyCo")
    api_session.add(company)
    api_session.flush()
    job = models.JobPosting(company_id=company.id, url="https://example.com/e", title="Eng")
    api_session.add(job)
    api_session.flush()

    resp = client.get(f"/jobs/{job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["must_haves"] == []
    assert data["nice_to_haves"] == []
    assert data["screening_questions"] == []


def test_get_job_detail_not_found(client):
    resp = client.get("/jobs/9999")
    assert resp.status_code == 404


def test_get_job_inspection_detail(client, api_session):
    """The inspection endpoint returns the nested JobDetailResponse with quality tiers."""
    company = models.Company(name="InspectCo")
    api_session.add(company)
    api_session.flush()
    job = models.JobPosting(
        company_id=company.id,
        url="paste:inspect1",
        title="Advocate",
        location="Remote",
        salary_min=80000,
        salary_max=100000,
        must_haves_json=json.dumps(["Degree in social work", "1-3 years experience", "Bilingual"]),
        nice_to_haves_json=json.dumps(["Spanish"]),
        screening_questions_json=json.dumps(["Why this role?"]),
    )
    api_session.add(job)
    api_session.flush()

    resp = client.get(f"/jobs/{job.id}/detail")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job"]["id"] == job.id
    assert data["job"]["title"] == "Advocate"
    assert data["job"]["company"] == "InspectCo"
    assert data["extracted"]["must_haves"] == [
        "Degree in social work",
        "1-3 years experience",
        "Bilingual",
    ]
    assert data["extracted"]["nice_to_haves"] == ["Spanish"]
    assert data["provenance"]["source_url"] == "paste:inspect1"
    assert data["quality"]["must_haves_count"] == 3
    assert data["quality"]["has_salary"] is True
    # 3 must-haves + salary -> rich tier
    assert data["quality"]["quality_tier"] == "rich"


def test_get_job_inspection_detail_not_found(client):
    resp = client.get("/jobs/9999/detail")
    assert resp.status_code == 404


# --- Applications ---

def test_list_applications_with_data(client, api_session):
    company = models.Company(name="AppCo")
    api_session.add(company)
    api_session.flush()
    job = models.JobPosting(company_id=company.id, url="https://example.com/a", title="Eng")
    api_session.add(job)
    api_session.flush()
    app_record = models.Application(job_posting_id=job.id, status="submitted")
    api_session.add(app_record)
    api_session.flush()

    resp = client.get("/applications")
    assert resp.status_code == 200
    apps = resp.json()
    assert len(apps) == 1
    assert apps[0]["status"] == "submitted"


# --- Artifact endpoint ---

def test_artifact_not_found(client, api_session):
    company = models.Company(name="ArtCo")
    api_session.add(company)
    api_session.flush()
    job = models.JobPosting(company_id=company.id, url="https://example.com/art")
    api_session.add(job)
    api_session.flush()

    resp = client.get(f"/artifact/{job.id}", params={"kind": "nonexistent"})
    assert resp.status_code == 404


def test_artifact_job_not_found(client):
    resp = client.get("/artifact/9999", params={"kind": "test"})
    assert resp.status_code == 404


# --- Export persistence ---

def _seed_job_and_blocks(session):
    company = models.Company(name="ExpCo")
    session.add(company)
    session.flush()
    job = models.JobPosting(
        company_id=company.id,
        url="https://x.test/j",
        title="Dev",
        location="Remote",
    )
    session.add(job)
    session.flush()
    blocks = [
        models.ResumeBlock(category="summary", text="Python developer."),
        models.ResumeBlock(
            category="experience",
            text="Built APIs.",
            job_title="Dev",
            company="Acme",
        ),
    ]
    session.add_all(blocks)
    session.flush()
    ids = (job.id, [b.id for b in blocks])
    session.commit()
    return ids


def test_export_persists_generated_resume(client, patched_settings):
    session = _TestSessionLocal()
    job_id, block_ids = _seed_job_and_blocks(session)

    resp = client.post("/export", json={
        "job_id": job_id, "block_ids": block_ids,
        "template": "classic", "format": "docx", "resume_version": "v1",
        "tailored": False,
    })
    assert resp.status_code == 200
    assert resp.headers["x-resume-version"] == "1"

    rows = session.query(models.GeneratedResume).filter_by(job_posting_id=job_id).all()
    assert len(rows) == 1
    assert rows[0].docx_path and rows[0].pdf_path is None
    session.close()


def test_job_resume_listing_and_detail(client, patched_settings):
    session = _TestSessionLocal()
    job_id, block_ids = _seed_job_and_blocks(session)
    for fmt in ("docx", "pdf"):  # same content twice -> one version, both formats
        client.post("/export", json={
            "job_id": job_id, "block_ids": block_ids, "template": "classic",
            "format": fmt, "resume_version": "v1", "tailored": False,
        })

    listing = client.get(f"/jobs/{job_id}/resumes").json()
    assert len(listing) == 1
    assert listing[0]["version"] == 1
    assert listing[0]["has_pdf"] and listing[0]["has_docx"]

    latest = client.get(f"/jobs/{job_id}/resumes/latest").json()
    assert latest["resume_text"]
    assert latest["block_ids"] == block_ids
    assert latest["missing_block_ids"] == []

    by_version = client.get(f"/jobs/{job_id}/resumes/1").json()
    assert by_version["version"] == 1

    assert client.get(f"/jobs/{job_id}/resumes/99").status_code == 404

    job_detail = client.get(f"/jobs/{job_id}").json()
    assert job_detail["latest_resume"]["version"] == 1
    session.close()


def test_job_without_resumes(client, patched_settings):
    session = _TestSessionLocal()
    job_id, _ = _seed_job_and_blocks(session)

    assert client.get(f"/jobs/{job_id}/resumes").json() == []
    assert client.get(f"/jobs/{job_id}/resumes/latest").status_code == 404
    assert client.get(f"/jobs/{job_id}").json()["latest_resume"] is None
    session.close()


def test_generated_resume_download(client, patched_settings):
    session = _TestSessionLocal()
    job_id, block_ids = _seed_job_and_blocks(session)
    client.post("/export", json={
        "job_id": job_id, "block_ids": block_ids, "template": "classic",
        "format": "docx", "resume_version": "v1", "tailored": False,
    })
    rid = client.get(f"/jobs/{job_id}/resumes").json()[0]["id"]

    ok = client.get(f"/generated-resumes/{rid}/download?format=docx")
    assert ok.status_code == 200
    assert "attachment" in ok.headers["content-disposition"]

    missing_fmt = client.get(f"/generated-resumes/{rid}/download?format=pdf")
    assert missing_fmt.status_code == 404

    import os
    row = session.get(models.GeneratedResume, rid)
    os.remove(row.docx_path)
    gone = client.get(f"/generated-resumes/{rid}/download?format=docx")
    assert gone.status_code == 404
    assert row.docx_path in gone.json()["detail"]
    session.close()


# --- Uploaded-resume persistence ---

def test_upload_stores_file_and_lists(client, patched_settings, monkeypatch):
    from backend.services.resume_converter import ResumeConverter
    monkeypatch.setattr(
        ResumeConverter,
        "parse_text_resume",
        lambda self, text: {
            "blocks": [
                {"category": "summary", "content": "Python dev", "tags": []}
            ],
            "metadata": {},
        },
    )

    resp = client.post(
        "/upload-resume",
        files={"file": ("my_resume.txt", b"Python dev resume text", "text/plain")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["upload_id"] > 0

    uploads = client.get("/uploaded-resumes").json()
    assert len(uploads) == 1
    assert uploads[0]["filename"] == "my_resume.txt"
    assert uploads[0]["block_count"] == 1

    dl = client.get(f"/uploaded-resumes/{uploads[0]['id']}/download")
    assert dl.status_code == 200
    assert dl.content == b"Python dev resume text"


def test_restore_resume_version_returns_200_and_404(client, patched_settings):
    session = _TestSessionLocal()
    job_id, block_ids = _seed_job_and_blocks(session)

    # Export to create version 1
    client.post("/export", json={
        "job_id": job_id, "block_ids": block_ids,
        "template": "classic", "format": "pdf",
        "resume_version": "v1", "tailored": False,
    })

    resp = client.post(f"/jobs/{job_id}/resumes/1/restore")
    assert resp.status_code == 200
    assert resp.json()["restored_version"] == 1

    not_found = client.post(f"/jobs/{job_id}/resumes/99/restore")
    assert not_found.status_code == 404
    session.close()


def test_upload_resume_reused_flag(client, patched_settings, monkeypatch):
    from backend.services.resume_converter import ResumeConverter
    monkeypatch.setattr(
        ResumeConverter,
        "parse_text_resume",
        lambda self, text: {
            "blocks": [{"category": "summary", "content": "Dev", "tags": []}],
            "metadata": {},
        },
    )
    content = b"same resume bytes"

    first = client.post(
        "/upload-resume",
        files={"file": ("r.txt", content, "text/plain")},
    )
    assert first.status_code == 201
    assert first.json().get("reused") is False

    second = client.post(
        "/upload-resume",
        files={"file": ("r_copy.txt", content, "text/plain")},
    )
    assert second.status_code == 201
    assert second.json().get("reused") is True

    uploads = client.get("/uploaded-resumes").json()
    assert len(uploads) == 1


def test_parse_then_confirm_links_upload(client, patched_settings, monkeypatch):
    from backend.services.resume_converter import ResumeConverter
    monkeypatch.setattr(
        ResumeConverter,
        "parse_text_resume",
        lambda self, text: {
            "blocks": [
                {"category": "summary", "content": "Python dev", "tags": []}
            ],
            "metadata": {},
        },
    )

    parsed = client.post(
        "/parse-resume",
        files={"file": ("r.txt", b"resume body", "text/plain")},
    ).json()
    upload_id = parsed["upload_id"]
    assert upload_id > 0

    confirm = client.post(
        "/confirm-resume-blocks",
        json={
            "blocks": [
                {
                    "category": "summary",
                    "content": "Python dev",
                    "tags": [],
                    "job_title": None,
                    "company": None,
                    "start_date": None,
                    "end_date": None,
                }
            ],
            "upload_id": upload_id,
        },
    )
    assert confirm.status_code == 201

    uploads = client.get("/uploaded-resumes").json()
    assert uploads[0]["block_count"] == 1
