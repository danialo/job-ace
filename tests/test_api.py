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
