"""Tests for the ExportService."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from backend.db.session import Base, engine, get_session
from backend.models.models import ResumeBlock
from backend.services.export import ExportService


@pytest.fixture(autouse=True)
def _setup_db():
    """Create tables for each test."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    with get_session() as session:
        yield session


@pytest.fixture
def sample_blocks(db: Session) -> list[int]:
    """Insert sample resume blocks and return their IDs."""
    blocks_data = [
        ResumeBlock(
            category="contact",
            tags="",
            text="Jane Doe\njane@example.com\n555-123-4567\nSan Francisco, CA",
        ),
        ResumeBlock(
            category="summary",
            tags="software-engineer",
            text="Experienced software engineer with 8 years of experience.",
        ),
        ResumeBlock(
            category="experience",
            tags="python,backend",
            text="- Designed and built REST APIs serving 10k requests/sec\n- Led migration from monolith to microservices",
            job_title="Senior Software Engineer",
            company="Acme Corp",
            start_date="Jan 2020",
            end_date="Present",
        ),
        ResumeBlock(
            category="education",
            tags="cs",
            text="Bachelor of Science in Computer Science",
            company="MIT",
            start_date="2012",
            end_date="2016",
        ),
        ResumeBlock(
            category="skills",
            tags="technical",
            text="Python, Go, PostgreSQL, Docker, Kubernetes, AWS",
        ),
    ]
    for block in blocks_data:
        db.add(block)
    db.flush()
    ids = [b.id for b in blocks_data]
    db.commit()
    return ids


def test_list_templates(db: Session):
    service = ExportService(db)
    templates = service.list_templates()
    assert len(templates) >= 1
    classic = next((t for t in templates if t["id"] == "classic"), None)
    assert classic is not None
    assert classic["name"] == "Classic"


def test_render_pdf_returns_pdf_bytes(db: Session, sample_blocks: list[int]):
    service = ExportService(db)
    pdf_bytes = service.render_pdf(job_id=0, block_ids=sample_blocks)
    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 100


def test_render_docx_returns_valid_bytes(db: Session, sample_blocks: list[int]):
    service = ExportService(db)
    docx_bytes = service.render_docx(job_id=0, block_ids=sample_blocks)
    # DOCX files are ZIP archives starting with PK
    assert docx_bytes[:2] == b"PK"
    assert len(docx_bytes) > 100


def test_render_no_blocks_raises(db: Session):
    service = ExportService(db)
    with pytest.raises(ValueError, match="No block IDs"):
        service.render_pdf(job_id=0, block_ids=[])


def test_render_missing_blocks_raises(db: Session):
    service = ExportService(db)
    with pytest.raises(ValueError, match="No blocks found"):
        service.render_pdf(job_id=0, block_ids=[99999])


def test_render_unknown_template_raises(db: Session, sample_blocks: list[int]):
    service = ExportService(db)
    with pytest.raises(ValueError, match="not found"):
        service.render_pdf(job_id=0, block_ids=sample_blocks, template="nonexistent")
