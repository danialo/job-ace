"""Tests for the ExportService."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.session import Base, engine, get_session
from backend.models.models import Artifact, Company, JobPosting, ResumeBlock
from backend.services.export import ExportService, _content_to_txt
from backend.models.resume_document import (
    BulletsContent,
    ItemsContent,
    ProseContent,
    SkillsContent,
    SkillsGroup,
)


@pytest.fixture
def db():
    """Isolated in-memory DB session — never touches the real ./db.sqlite3."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


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


# ---------------------------------------------------------------------------
# _content_to_txt unit tests
# ---------------------------------------------------------------------------

class TestContentToTxt:
    def test_bullets_prefixed_with_dash(self):
        content = BulletsContent(bullets=["Led team of five", "Delivered on time"])
        txt = _content_to_txt(content)
        assert txt == "- Led team of five\n- Delivered on time"

    def test_prose_paragraphs_blank_line_separated(self):
        content = ProseContent(paragraphs=["First paragraph.", "Second paragraph."])
        txt = _content_to_txt(content)
        assert txt == "First paragraph.\n\nSecond paragraph."

    def test_skills_labeled_groups(self):
        content = SkillsContent(groups=[
            SkillsGroup(label="Languages", items=["Python", "Go"]),
            SkillsGroup(label="Infra", items=["Docker", "K8s"]),
        ])
        txt = _content_to_txt(content)
        assert "Languages: Python, Go" in txt
        assert "Infra: Docker, K8s" in txt

    def test_skills_unlabeled_group_inline(self):
        content = SkillsContent(groups=[
            SkillsGroup(label=None, items=["Python", "Go", "PostgreSQL"]),
        ])
        txt = _content_to_txt(content)
        assert txt == "Python, Go, PostgreSQL"

    def test_items_one_per_line(self):
        content = ItemsContent(items=["CompTIA Network+", "AWS Solutions Architect"])
        txt = _content_to_txt(content)
        assert txt == "CompTIA Network+\nAWS Solutions Architect"


# ---------------------------------------------------------------------------
# render_txt integration tests
# ---------------------------------------------------------------------------

class TestRenderTxt:
    def test_returns_string(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert isinstance(result, str)

    def test_ends_with_newline(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert result.endswith("\n")

    def test_contains_name(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert "Jane Doe" in result

    def test_contains_contact_info(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert "jane@example.com" in result
        assert "555-123-4567" in result

    def test_section_headings_uppercase(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert "EXPERIENCE" in result
        assert "EDUCATION" in result
        assert "SKILLS" in result

    def test_section_headings_have_underlines(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        lines = result.splitlines()
        for i, line in enumerate(lines):
            if line == "EXPERIENCE":
                assert i + 1 < len(lines)
                assert set(lines[i + 1]) == {"-"}
                break
        else:
            pytest.fail("EXPERIENCE heading not found")

    def test_bullets_rendered_with_dash(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert "- Designed and built REST APIs" in result
        assert "- Led migration from monolith" in result

    def test_no_html_tags(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert "<" not in result
        assert ">" not in result

    def test_entry_header_in_output(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert "Senior Software Engineer" in result
        assert "Acme Corp" in result

    def test_dates_in_output(self, db: Session, sample_blocks: list[int]):
        service = ExportService(db)
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert "Present" in result

    def test_no_blocks_raises(self, db: Session):
        service = ExportService(db)
        with pytest.raises(ValueError, match="No block IDs"):
            service.render_txt(job_id=0, block_ids=[])


# ---------------------------------------------------------------------------
# Artifact persistence tests
# ---------------------------------------------------------------------------

@pytest.fixture
def job_with_posting(db: Session) -> JobPosting:
    """Create a minimal JobPosting for artifact persistence tests."""
    company = Company(name="Artifact Corp")
    db.add(company)
    db.flush()
    posting = JobPosting(
        title="Test Role",
        company_id=company.id,
        location="Remote",
        url="https://artifact.example.com/jobs/1",
    )
    db.add(posting)
    db.flush()
    db.commit()
    return posting


class TestArtifactPersistence:
    def test_resume_document_json_persisted(
        self, db: Session, sample_blocks: list[int], job_with_posting: JobPosting, tmp_path, monkeypatch
    ):
        """render_txt with a valid job_id should persist resume_document.json."""
        import backend.config as cfg

        # Redirect data_root to tmp_path so we don't pollute real storage
        mock_settings = cfg.Settings(
            data_root=tmp_path,
            database_url="sqlite:///:memory:",
        )
        monkeypatch.setattr(cfg, "get_settings", lambda: mock_settings)

        # Also patch the artifact manager's settings reference
        import backend.services.artifacts as art_mod
        monkeypatch.setattr(art_mod, "settings", mock_settings)

        service = ExportService(db)
        service.render_txt(
            job_id=job_with_posting.id,
            block_ids=sample_blocks,
        )

        # Artifact record should exist in DB
        artifact = db.query(Artifact).filter(
            Artifact.job_posting_id == job_with_posting.id,
            Artifact.kind == "resume_document",
        ).first()
        assert artifact is not None, "resume_document artifact not found in DB"

        # File should exist and be valid JSON
        artifact_path = artifact.path
        content = open(artifact_path).read()
        doc_json = json.loads(content)
        assert "basics" in doc_json
        assert "sections" in doc_json
        assert "metadata" in doc_json

    def test_persist_skipped_when_no_job(
        self, db: Session, sample_blocks: list[int]
    ):
        """render_txt with job_id=0 (non-existent) should not raise."""
        service = ExportService(db)
        # Should succeed silently even though job 0 doesn't exist
        result = service.render_txt(job_id=0, block_ids=sample_blocks)
        assert isinstance(result, str)
