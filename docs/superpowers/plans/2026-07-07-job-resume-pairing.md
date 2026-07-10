# Job + Resume Pairing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist generated resumes attached to their job (versioned, restorable, downloadable) and store uploaded resume files in Resume Intake, so the JD and the resume built for it are always found together.

**Architecture:** Two new SQLAlchemy tables (`generated_resume`, `uploaded_resume`) auto-created by `create_all()`. A new `ResumeStoreService` owns persistence/versioning/restore. `/export` persists before streaming; upload endpoints persist the original file. Frontend adds a resume panel to the job review modal, a restore flow in the Tailor tab, and an uploaded-resumes list in Resume Intake.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 mapped_column style, SQLite, pytest, vanilla JS frontend.

**Spec:** `specs/job-resume-pairing.md` (committed as 6debdf8).

## Global Constraints

- Do NOT develop in the live checkout while the service runs from it — work in a git worktree on branch `feat/job-resume-pairing` (create via superpowers:using-git-worktrees at execution start).
- Tests run ONLY against in-memory DB + `patched_settings` tmp data_root (existing conftest fixtures). Never point tests at `/var/lib/jobace` data. Snapshot the live DB before running any suite from a directory that could see it.
- Git commits are gated by the PreToolUse write-guard: commits are deliberate checkpoints — run them with the `CLAUDE_GH_WORKER=1` marker or delegate to the gh-worker agent, per the established workflow. Final push/PR goes through gh-worker (master ruleset: 1 approval + CI `test` check).
- No hardcoded IPs anywhere — localhost only (project rule).
- Follow existing code style: raw-dict responses for GET list/detail endpoints (like `/jobs`), Pydantic models for request bodies, `Mapped[]`/`mapped_column` models, module-level `settings = get_settings()` in services that write files (mirrors `artifacts.py`).
- Run `ruff check .` before each commit.

## File Structure

- `backend/models/models.py` — add `GeneratedResume`, `UploadedResume` (modify)
- `backend/services/resume_store.py` — new service: versioning, content-sha merge, restore payloads, upload storage (create)
- `backend/services/export.py` — hoist `_load_tailored_overrides` to module function (modify)
- `backend/api/app.py` — export persistence, new GET endpoints, upload wiring (modify)
- `backend/models/schemas.py` — `upload_id` fields (modify)
- `frontend/index.html` — resume panel hooks, tailor banner, uploaded list container (modify)
- `frontend/static/js/app.js` — panel render, restore flow, uploaded list (modify)
- `tests/test_resume_store.py` — service tests (create)
- `tests/test_api.py` — endpoint tests (modify)
- `tests/conftest.py` — patch new module's settings (modify)

---

### Task 1: Models — `GeneratedResume` and `UploadedResume`

**Files:**
- Modify: `backend/models/models.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Produces: `models.GeneratedResume(job_posting_id, version, block_ids_json, overrides_json, tailored, template, resume_text, pdf_path, docx_path, content_sha, created_at)` with `JobPosting.generated_resumes` relationship; `models.UploadedResume(filename, path, sha256, size_bytes, block_ids_json, created_at)`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v -k "generated_resume or uploaded_resume"`
Expected: FAIL with `AttributeError: module 'backend.models.models' has no attribute 'GeneratedResume'`

- [ ] **Step 3: Implement the models** — in `backend/models/models.py`, add `Boolean` to the sqlalchemy import, add to `JobPosting`:

```python
    generated_resumes: Mapped[list["GeneratedResume"]] = relationship(
        "GeneratedResume", back_populates="job_posting", order_by="GeneratedResume.version"
    )
```

and append at the end of the file:

```python
class GeneratedResume(Base):
    """A resume generated (exported) for a specific job — the pairing record."""

    __tablename__ = "generated_resume"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    block_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    overrides_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    tailored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    template: Mapped[str] = mapped_column(String, nullable=False, default="classic")
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[Optional[str]] = mapped_column(Text)
    docx_path: Mapped[Optional[str]] = mapped_column(Text)
    content_sha: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    job_posting: Mapped[JobPosting] = relationship("JobPosting", back_populates="generated_resumes")

    __table_args__ = (
        UniqueConstraint("job_posting_id", "version", name="uq_generated_resume_job_version"),
    )


class UploadedResume(Base):
    """An original resume file uploaded in Resume Intake. Deliberately not job-linked."""

    __tablename__ = "uploaded_resume"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    block_ids_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (all, including pre-existing)

- [ ] **Step 5: Commit**

```bash
git add backend/models/models.py tests/test_models.py
git commit -m "feat: add GeneratedResume and UploadedResume models"
```

---

### Task 2: ResumeStoreService — save generated resumes (versioning + format merge)

**Files:**
- Create: `backend/services/resume_store.py`
- Modify: `backend/services/export.py` (hoist override loader)
- Modify: `tests/conftest.py` (patch new module settings)
- Create: `tests/test_resume_store.py`

**Interfaces:**
- Consumes: `models.GeneratedResume` (Task 1), `ArtifactManager.write_bytes(job_posting, kind, relative_path, content) -> Path`.
- Produces: `load_tailored_overrides(db, job_id) -> Dict[int, str]` (module function in `export.py`); `ResumeStoreService(db).save_generated(job_id: int, block_ids: List[int], tailored: bool, template: str, fmt: str, data: bytes) -> models.GeneratedResume`.

- [ ] **Step 1: Hoist the override loader.** In `backend/services/export.py`, add a module-level function (below the imports, above the HTML helpers) and make the method delegate to it:

```python
def load_tailored_overrides(db: Session, job_id: int) -> Dict[int, str]:
    """Load the current per-job tailored block text written by the tailor step."""
    job = db.get(models.JobPosting, job_id)
    if not job or not job.jd_json_path:
        return {}
    path = Path(job.jd_json_path).parent / "tailored_blocks.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items() if v}
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
```

and replace the body of `ExportService._load_tailored_overrides` with:

```python
    def _load_tailored_overrides(self, job_id: int) -> Dict[int, str]:
        return load_tailored_overrides(self.db, job_id)
```

Run: `pytest tests/test_export.py -v` — Expected: PASS (pure refactor).

- [ ] **Step 2: Patch settings for the new module.** In `tests/conftest.py` `patched_settings`, extend the `with` block:

```python
    with patch("backend.services.artifacts.settings", settings), \
         patch("backend.services.resume_store.settings", settings), \
         patch("backend.config.get_settings", return_value=settings):
        yield settings
```

(This will fail to import until Step 4 creates the module — that is expected while the failing test is red.)

- [ ] **Step 3: Write the failing tests** — create `tests/test_resume_store.py`:

```python
"""Tests for ResumeStoreService — generated-resume persistence and versioning."""
from __future__ import annotations

import json

from backend.models import models
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_resume_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.resume_store'`

- [ ] **Step 5: Implement the service** — create `backend/services/resume_store.py`:

```python
"""Resume Store Service.

Owns the pairing record between a job posting and the resumes generated for
it (versioned, format-merged) plus original uploaded resume files.
See specs/job-resume-pairing.md.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import models
from backend.services.artifacts import ArtifactManager
from backend.services.export import load_tailored_overrides

settings = get_settings()


class ResumeStoreService:
    def __init__(self, db: Session):
        self.db = db
        self.artifacts = ArtifactManager(db)

    # ------------------------------------------------------------------
    # Generated resumes (job-linked)
    # ------------------------------------------------------------------

    def save_generated(
        self,
        job_id: int,
        block_ids: List[int],
        tailored: bool,
        template: str,
        fmt: str,
        data: bytes,
    ) -> models.GeneratedResume:
        """Persist an exported resume for a job.

        Same content (blocks + overrides + template) as the job's latest
        version fills the missing format on that version; any content change
        allocates a new version. Never mutates older rows.
        """
        if fmt not in ("pdf", "docx"):
            raise ValueError(f"Unsupported format: {fmt}")
        job = self.db.get(models.JobPosting, job_id)
        if not job:
            raise ValueError(f"Job posting {job_id} not found")

        overrides = load_tailored_overrides(self.db, job_id) if tailored else {}
        resume_text = self._assemble_text(block_ids, overrides)
        content_sha = self._content_sha(block_ids, overrides, template, tailored)

        latest = self._latest(job_id)
        if latest and latest.content_sha == content_sha:
            row = latest
        else:
            row = models.GeneratedResume(
                job_posting_id=job_id,
                version=(latest.version + 1) if latest else 1,
                block_ids_json=json.dumps(block_ids),
                overrides_json=json.dumps({str(k): v for k, v in overrides.items()}),
                tailored=tailored,
                template=template,
                resume_text=resume_text,
                content_sha=content_sha,
            )
            self.db.add(row)
            self.db.flush()

        path = self.artifacts.write_bytes(
            job, f"resume_export_{fmt}", f"exports/resume_v{row.version}.{fmt}", data
        )
        if fmt == "pdf":
            row.pdf_path = str(path)
        else:
            row.docx_path = str(path)
        self.db.flush()
        return row

    def list_versions(self, job_id: int) -> List[dict]:
        rows = self.db.scalars(
            select(models.GeneratedResume)
            .where(models.GeneratedResume.job_posting_id == job_id)
            .order_by(models.GeneratedResume.version.desc())
        ).all()
        return [self._summary(row) for row in rows]

    def get_version_detail(self, job_id: int, version: Optional[int] = None) -> Optional[dict]:
        """Full restore payload for one version (latest when version is None)."""
        stmt = select(models.GeneratedResume).where(
            models.GeneratedResume.job_posting_id == job_id
        )
        if version is None:
            stmt = stmt.order_by(models.GeneratedResume.version.desc()).limit(1)
        else:
            stmt = stmt.where(models.GeneratedResume.version == version)
        row = self.db.scalars(stmt).first()
        if not row:
            return None

        block_ids = json.loads(row.block_ids_json)
        existing = set(
            self.db.scalars(
                select(models.ResumeBlock.id).where(models.ResumeBlock.id.in_(block_ids))
            ).all()
        ) if block_ids else set()

        detail = self._summary(row)
        detail.update({
            "resume_text": row.resume_text,
            "block_ids": [b for b in block_ids if b in existing],
            "missing_block_ids": [b for b in block_ids if b not in existing],
            "overrides": json.loads(row.overrides_json),
        })
        return detail

    def latest_summary(self, job_id: int) -> Optional[dict]:
        latest = self._latest(job_id)
        return self._summary(latest) if latest else None

    def _latest(self, job_id: int) -> Optional[models.GeneratedResume]:
        return self.db.scalars(
            select(models.GeneratedResume)
            .where(models.GeneratedResume.job_posting_id == job_id)
            .order_by(models.GeneratedResume.version.desc())
            .limit(1)
        ).first()

    def _summary(self, row: models.GeneratedResume) -> dict:
        return {
            "id": row.id,
            "version": row.version,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "template": row.template,
            "tailored": row.tailored,
            "has_pdf": bool(row.pdf_path),
            "has_docx": bool(row.docx_path),
            "block_count": len(json.loads(row.block_ids_json)),
        }

    def _assemble_text(self, block_ids: List[int], overrides: Dict[int, str]) -> str:
        blocks = self.db.scalars(
            select(models.ResumeBlock).where(models.ResumeBlock.id.in_(block_ids))
        ).all()
        by_id = {b.id: b for b in blocks}
        missing = [i for i in block_ids if i not in by_id]
        if missing:
            raise ValueError(f"Resume blocks missing: {missing}")
        return "\n\n".join(overrides.get(i, by_id[i].text) for i in block_ids)

    @staticmethod
    def _content_sha(
        block_ids: List[int], overrides: Dict[int, str], template: str, tailored: bool
    ) -> str:
        payload = json.dumps(
            {
                "block_ids": block_ids,
                "overrides": {str(k): v for k, v in overrides.items()},
                "template": template,
                "tailored": tailored,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

(`list_versions`, `get_version_detail`, and `latest_summary` are exercised in Task 3's tests; implementing them here keeps the file whole.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_resume_store.py tests/test_export.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/resume_store.py backend/services/export.py tests/test_resume_store.py tests/conftest.py
git commit -m "feat: ResumeStoreService — versioned generated-resume persistence"
```

---

### Task 3: ResumeStoreService — restore payloads and version listing

**Files:**
- Modify: `tests/test_resume_store.py`
- Modify: `backend/services/resume_store.py` (only if Task 2's implementation has gaps)

**Interfaces:**
- Produces (verified): `list_versions(job_id) -> List[dict]` (newest first), `get_version_detail(job_id, version=None) -> dict | None` with keys `id, version, created_at, template, tailored, has_pdf, has_docx, block_count, resume_text, block_ids, missing_block_ids, overrides`, `latest_summary(job_id) -> dict | None`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_resume_store.py`:

```python
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
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_resume_store.py -v`
Expected: PASS if Task 2's implementation is complete; if any fail, fix `resume_store.py` minimally until green.

- [ ] **Step 3: Commit**

```bash
git add tests/test_resume_store.py backend/services/resume_store.py
git commit -m "test: restore payloads, version listing, deleted-block reporting"
```

---

### Task 4: ResumeStoreService — uploaded resume storage

**Files:**
- Modify: `backend/services/resume_store.py`
- Modify: `tests/test_resume_store.py`

**Interfaces:**
- Produces: `save_upload(filename: str, content: bytes) -> tuple[models.UploadedResume, bool]` (row, reused — reused=True when a byte-identical file already exists), `link_blocks(upload_id: int, block_ids: List[int]) -> None`, `list_uploads() -> List[dict]` with keys `id, filename, size_bytes, created_at, block_count`, `get_upload(upload_id: int) -> models.UploadedResume | None`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_resume_store.py`:

```python
def test_save_upload_persists_file(db_session, patched_settings):
    store = ResumeStoreService(db_session)
    row, reused = store.save_upload("My Resume.pdf", b"%PDF real content")

    assert reused is False
    assert row.filename == "My Resume.pdf"
    assert row.size_bytes == len(b"%PDF real content")
    with open(row.path, "rb") as fh:
        assert fh.read() == b"%PDF real content"
    assert "resumes" in row.path


def test_save_upload_identical_file_reuses_row(db_session, patched_settings):
    store = ResumeStoreService(db_session)
    first, _ = store.save_upload("resume.pdf", b"same bytes")
    second, reused = store.save_upload("renamed.pdf", b"same bytes")

    assert reused is True
    assert second.id == first.id
    assert db_session.query(models.UploadedResume).count() == 1


def test_link_blocks_overwrites_with_latest(db_session, patched_settings):
    store = ResumeStoreService(db_session)
    row, _ = store.save_upload("resume.pdf", b"content")

    store.link_blocks(row.id, [1, 2, 3])
    assert json.loads(row.block_ids_json) == [1, 2, 3]
    store.link_blocks(row.id, [4, 5])
    assert json.loads(row.block_ids_json) == [4, 5]


def test_list_uploads(db_session, patched_settings):
    store = ResumeStoreService(db_session)
    row, _ = store.save_upload("resume.pdf", b"content")
    store.link_blocks(row.id, [1, 2])

    uploads = store.list_uploads()
    assert len(uploads) == 1
    assert uploads[0]["filename"] == "resume.pdf"
    assert uploads[0]["block_count"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_resume_store.py -v -k upload`
Expected: FAIL with `AttributeError: 'ResumeStoreService' object has no attribute 'save_upload'`

- [ ] **Step 3: Implement** — append to `ResumeStoreService` in `backend/services/resume_store.py`:

```python
    # ------------------------------------------------------------------
    # Uploaded resumes (Resume Intake — deliberately not job-linked)
    # ------------------------------------------------------------------

    def save_upload(self, filename: str, content: bytes) -> tuple[models.UploadedResume, bool]:
        """Store an uploaded resume file. Byte-identical re-uploads reuse the row."""
        sha256 = hashlib.sha256(content).hexdigest()
        existing = self.db.scalars(
            select(models.UploadedResume).where(models.UploadedResume.sha256 == sha256)
        ).first()
        if existing:
            return existing, True

        resumes_dir = settings.data_root / "resumes"
        resumes_dir.mkdir(parents=True, exist_ok=True)
        safe_name = filename.replace("/", "_").replace("\\", "_")
        path = resumes_dir / f"{sha256[:12]}_{safe_name}"
        path.write_bytes(content)

        row = models.UploadedResume(
            filename=filename,
            path=str(path),
            sha256=sha256,
            size_bytes=len(content),
        )
        self.db.add(row)
        self.db.flush()
        return row, False

    def link_blocks(self, upload_id: int, block_ids: List[int]) -> None:
        """Record which blocks came from this upload (latest confirmation wins)."""
        row = self.db.get(models.UploadedResume, upload_id)
        if not row:
            raise ValueError(f"Uploaded resume {upload_id} not found")
        row.block_ids_json = json.dumps(block_ids)
        self.db.flush()

    def list_uploads(self) -> List[dict]:
        rows = self.db.scalars(
            select(models.UploadedResume).order_by(models.UploadedResume.id.desc())
        ).all()
        return [
            {
                "id": r.id,
                "filename": r.filename,
                "size_bytes": r.size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "block_count": len(json.loads(r.block_ids_json)) if r.block_ids_json else 0,
            }
            for r in rows
        ]

    def get_upload(self, upload_id: int) -> Optional[models.UploadedResume]:
        return self.db.get(models.UploadedResume, upload_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_resume_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/resume_store.py tests/test_resume_store.py
git commit -m "feat: uploaded-resume storage with sha256 dedupe"
```

---

### Task 5: `/export` persists before streaming

**Files:**
- Modify: `backend/api/app.py` (`export_resume` handler)
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `ResumeStoreService.save_generated` (Task 2).
- Produces: `/export` response gains header `X-Resume-Version: <int>`; persistence failure → 500 with no file streamed.

- [ ] **Step 1: Write the failing test** — append to `tests/test_api.py` (it already has `client` + in-memory DB via the autouse fixture; add `patched_settings` for file writes):

```python
def _seed_job_and_blocks(session):
    company = models.Company(name="ExpCo")
    session.add(company)
    session.flush()
    job = models.JobPosting(company_id=company.id, url="https://x.test/j", title="Dev", location="Remote")
    session.add(job)
    session.flush()
    blocks = [
        models.ResumeBlock(category="summary", text="Python developer."),
        models.ResumeBlock(category="experience", text="Built APIs.", job_title="Dev", company="Acme"),
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
```

(`tests/test_api.py` already provides the `client` fixture at line ~63 and the module-global `_TestSessionLocal`; the autouse `_setup_test_db` fixture gives each test a fresh in-memory DB.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v -k export_persists`
Expected: FAIL — either `KeyError: 'x-resume-version'` or empty `generated_resume` table.

- [ ] **Step 3: Implement** — in `backend/api/app.py`, import the service (`from backend.services.resume_store import ResumeStoreService`) and modify `export_resume`: after the render `try/except` block and before building the `Response`, add:

```python
    store = ResumeStoreService(db)
    try:
        row = store.save_generated(
            job_id=payload.job_id,
            block_ids=payload.block_ids,
            tailored=payload.tailored,
            template=payload.template,
            fmt=fmt,
            data=data,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Resume rendered but could not be saved: {exc}"
        ) from exc
```

and add the version header to the response:

```python
    filename = f"resume_v{row.version}.{ext}"
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Resume-Version": str(row.version),
        },
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_api.py tests/test_export.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/app.py tests/test_api.py
git commit -m "feat: /export persists the generated resume before streaming"
```

---

### Task 6: Job-resume read endpoints + `latest_resume` on job detail

**Files:**
- Modify: `backend/api/app.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `ResumeStoreService.list_versions / get_version_detail / latest_summary / get_upload` (Tasks 2–4), `models.GeneratedResume`.
- Produces: `GET /jobs/{id}/resumes`, `GET /jobs/{id}/resumes/latest`, `GET /jobs/{id}/resumes/{version}`, `GET /generated-resumes/{id}/download?format=pdf|docx`; `GET /jobs/{id}` response gains `"latest_resume"` key (summary dict or null).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_api.py`:

```python
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
    row = session.query(models.GeneratedResume).get(rid)
    os.remove(row.docx_path)
    gone = client.get(f"/generated-resumes/{rid}/download?format=docx")
    assert gone.status_code == 404
    assert row.docx_path in gone.json()["detail"]
    session.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v -k "job_resume or job_without or generated_resume_download"`
Expected: FAIL with 404s on the new routes / `KeyError: 'latest_resume'`.

- [ ] **Step 3: Implement** — in `backend/api/app.py`:

In `get_job` (the `GET /jobs/{job_id}` handler), add to the returned dict:

```python
        "latest_resume": ResumeStoreService(db).latest_summary(job.id),
```

Add new routes (place after `get_job`; **`/resumes/latest` must be declared before `/resumes/{version}`** so FastAPI does not parse "latest" as an int):

```python
@app.get("/jobs/{job_id}/resumes")
def list_job_resumes(job_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """List all generated resume versions for a job, newest first."""
    if not db.get(models.JobPosting, job_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return ResumeStoreService(db).list_versions(job_id)


@app.get("/jobs/{job_id}/resumes/latest")
def get_latest_job_resume(job_id: int, db: Session = Depends(get_db)) -> dict:
    """Full detail of the latest generated resume for a job (restore payload)."""
    detail = ResumeStoreService(db).get_version_detail(job_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No generated resume for this job")
    return detail


@app.get("/jobs/{job_id}/resumes/{version}")
def get_job_resume_version(job_id: int, version: int, db: Session = Depends(get_db)) -> dict:
    """Full detail of one generated resume version."""
    detail = ResumeStoreService(db).get_version_detail(job_id, version=version)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {version} not found for this job")
    return detail


@app.get("/generated-resumes/{resume_id}/download")
def download_generated_resume(resume_id: int, format: str = "pdf", db: Session = Depends(get_db)) -> FileResponse:
    """Stream a stored generated-resume file."""
    row = db.get(models.GeneratedResume, resume_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated resume not found")
    if format == "pdf":
        path, media_type = row.pdf_path, "application/pdf"
    elif format == "docx":
        path, media_type = row.docx_path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise HTTPException(status_code=400, detail="format must be 'pdf' or 'docx'")
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No {format} stored for this version")
    if not Path(path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File missing from disk: {path}")
    return FileResponse(path, media_type=media_type, filename=Path(path).name)
```

Add imports at the top of `app.py` as needed: `from fastapi.responses import FileResponse` and `from pathlib import Path` (check both — `Path` may already be imported).

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/app.py tests/test_api.py
git commit -m "feat: job-resume read endpoints + latest_resume on job detail"
```

---

### Task 7: Persist uploads through the intake endpoints

**Files:**
- Modify: `backend/api/app.py` (`parse_resume`, `confirm_resume_blocks`, `upload_resume` + two new GET routes)
- Modify: `backend/models/schemas.py` (`ParseResumeResponse.upload_id`, `ConfirmResumeBlocksRequest.upload_id`)
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `ResumeStoreService.save_upload / link_blocks / list_uploads / get_upload` (Task 4).
- Produces: `POST /parse-resume` response gains `upload_id: int`; `POST /confirm-resume-blocks` accepts optional `upload_id`; `POST /upload-resume` persists file + links blocks; `GET /uploaded-resumes`, `GET /uploaded-resumes/{id}/download`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_api.py`. The parse endpoints call the LLM-backed converter; stub it the way existing upload tests in this file do (follow the file's existing mock pattern for `ResumeConverter` / LLM client — if none exists, patch `backend.api.app.ResumeConverter.parse_text_resume` to return a fixed block dict):

```python
def test_upload_stores_file_and_lists(client, patched_settings, monkeypatch):
    from backend.services.resume_converter import ResumeConverter
    monkeypatch.setattr(
        ResumeConverter, "parse_text_resume",
        lambda self, text: {"blocks": [{"category": "summary", "content": "Python dev", "tags": []}], "metadata": {}},
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


def test_parse_then_confirm_links_upload(client, patched_settings, monkeypatch):
    from backend.services.resume_converter import ResumeConverter
    monkeypatch.setattr(
        ResumeConverter, "parse_text_resume",
        lambda self, text: {"blocks": [{"category": "summary", "content": "Python dev", "tags": []}], "metadata": {}},
    )

    parsed = client.post(
        "/parse-resume",
        files={"file": ("r.txt", b"resume body", "text/plain")},
    ).json()
    upload_id = parsed["upload_id"]
    assert upload_id > 0

    confirm = client.post("/confirm-resume-blocks", json={
        "blocks": [{"category": "summary", "content": "Python dev", "tags": [],
                    "job_title": None, "company": None, "start_date": None, "end_date": None}],
        "upload_id": upload_id,
    })
    assert confirm.status_code == 201

    uploads = client.get("/uploaded-resumes").json()
    assert uploads[0]["block_count"] == 1
```

(The confirm payload matches `ConfirmBlockData` in `backend/models/schemas.py`: required `category`, `tags`, `content`; optional `job_title`, `company`, `start_date`, `end_date`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v -k "upload_stores or parse_then_confirm"`
Expected: FAIL — `KeyError: 'upload_id'` / 404 on `/uploaded-resumes`.

- [ ] **Step 3: Implement** — in `backend/models/schemas.py`: add `upload_id: Optional[int] = None` to both `ParseResumeResponse` and `ConfirmResumeBlocksRequest`.

In `backend/api/app.py`:

**`upload_resume`**: after reading `content = await file.read()`, add:

```python
    store = ResumeStoreService(db)
    upload_row, _reused = store.save_upload(file.filename, content)
```

and after the blocks are flushed (before `db.commit()`):

```python
        store.link_blocks(upload_row.id, block_ids)
```

and add `"upload_id": upload_row.id` to the success response dict.

**`parse_resume`**: after reading the file content, add the same `save_upload` call (`upload_row, _reused = ResumeStoreService(db).save_upload(file.filename, content)`, followed by `db.commit()` so the row survives the request), and include `upload_id=upload_row.id` in the returned `ParseResumeResponse`.

**`confirm_resume_blocks`**: after the blocks are flushed, before `db.commit()`:

```python
        if payload.upload_id:
            ResumeStoreService(db).link_blocks(payload.upload_id, block_ids)
```

**New routes:**

```python
@app.get("/uploaded-resumes")
def list_uploaded_resumes(db: Session = Depends(get_db)) -> list[dict]:
    """List original resume files uploaded in Resume Intake."""
    return ResumeStoreService(db).list_uploads()


@app.get("/uploaded-resumes/{upload_id}/download")
def download_uploaded_resume(upload_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Stream an original uploaded resume file."""
    row = ResumeStoreService(db).get_upload(upload_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded resume not found")
    if not Path(row.path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File missing from disk: {row.path}")
    return FileResponse(row.path, filename=row.filename)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/app.py backend/models/schemas.py tests/test_api.py
git commit -m "feat: persist uploaded resume files through intake endpoints"
```

---

### Task 8: Frontend — Generated Resume panel in the job review modal

**Files:**
- Modify: `frontend/static/js/app.js` (`reviewJob`, new helpers)

**Interfaces:**
- Consumes: `GET /jobs/{id}/resumes`, `GET /jobs/{id}/resumes/latest`, `GET /generated-resumes/{id}/download` (Task 6).
- Produces: `loadSavedResumeInTailor(jobId)` global (Task 9 wires its target); `downloadGeneratedResume(resumeId, format)` global.

No JS unit-test harness exists in this repo — verification is manual (Step 3).

- [ ] **Step 1: Implement.** In `frontend/static/js/app.js`, inside `reviewJob(jobId)`, after the `body.innerHTML = ...` assignment, append:

```javascript
        // Generated Resume panel — the resume(s) built for this job
        body.insertAdjacentHTML('beforeend', '<div id="job-resume-panel"><h4>Generated Resume</h4><p class="text-muted">Loading…</p></div>');
        renderJobResumePanel(jobId);
```

Add the new functions after `closeJobReviewModal()`:

```javascript
async function renderJobResumePanel(jobId) {
    const panel = document.getElementById('job-resume-panel');
    if (!panel) return;
    try {
        const latestResp = await fetch(`${API_BASE}/jobs/${jobId}/resumes/latest`);
        if (latestResp.status === 404) {
            panel.innerHTML = '<h4>Generated Resume</h4><p class="text-muted">No resume generated for this job yet.</p>';
            return;
        }
        if (!latestResp.ok) throw new Error(`status ${latestResp.status}`);
        const latest = await latestResp.json();
        const versionsResp = await fetch(`${API_BASE}/jobs/${jobId}/resumes`);
        const versions = versionsResp.ok ? await versionsResp.json() : [];

        const fmtButtons = [
            latest.has_pdf ? `<button type="button" class="btn btn-secondary" onclick="downloadGeneratedResume(${latest.id}, 'pdf')">Download PDF</button>` : '',
            latest.has_docx ? `<button type="button" class="btn btn-secondary" onclick="downloadGeneratedResume(${latest.id}, 'docx')">Download DOCX</button>` : '',
        ].join(' ');

        const history = versions.length > 1
            ? `<details><summary>${versions.length} versions</summary><ul class="job-review-list">${versions.map(v =>
                  `<li>v${v.version} — ${new Date(v.created_at).toLocaleDateString()} (${v.template}${v.tailored ? ', tailored' : ''})`
                  + (v.has_pdf ? ` <a href="#" onclick="downloadGeneratedResume(${v.id}, 'pdf'); return false;">PDF</a>` : '')
                  + (v.has_docx ? ` <a href="#" onclick="downloadGeneratedResume(${v.id}, 'docx'); return false;">DOCX</a>` : '')
                  + '</li>').join('')}</ul></details>`
            : '';

        panel.innerHTML = `
            <h4>Generated Resume</h4>
            <p><strong>v${latest.version}</strong> — ${new Date(latest.created_at).toLocaleString()}${latest.tailored ? ' (tailored)' : ''}, template: ${esc(latest.template)}</p>
            <p>${fmtButtons}
               <button type="button" class="btn btn-primary" onclick="loadSavedResumeInTailor(${jobId})">Load in Tailor</button></p>
            <pre class="resume-preview">${esc(latest.resume_text)}</pre>
            ${history}
        `;
    } catch (error) {
        panel.innerHTML = `<h4>Generated Resume</h4><p style="color:#c0392b;">Could not load resume: ${esc(error.message)}</p>`;
    }
}

async function downloadGeneratedResume(resumeId, format) {
    try {
        const response = await fetch(`${API_BASE}/generated-resumes/${resumeId}/download?format=${format}`);
        if (!response.ok) {
            const err = await response.json();
            alert('Download failed: ' + (err.detail || 'Unknown error'));
            return;
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const disposition = response.headers.get('content-disposition') || '';
        const match = disposition.match(/filename="(.+)"/);
        a.download = match ? match[1] : `resume.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (error) {
        alert('Download error: ' + error.message);
    }
}
```

(`loadSavedResumeInTailor` is defined in Task 9; if executing tasks out of order, add a temporary `function loadSavedResumeInTailor() { alert('Coming in Task 9'); }`.)

- [ ] **Step 2: Lint/sanity** — Run: `node --check frontend/static/js/app.js`
Expected: no output (parses cleanly).

- [ ] **Step 3: Manual verification** — start the dev server (`./start.sh` in the worktree with a scratch DB/data_root, NOT the live one), capture a job, tailor + export, then open **Capture Job → Review capture**: the panel shows the resume text, version line, and working download buttons; a job without exports shows "No resume generated for this job yet."

- [ ] **Step 4: Commit**

```bash
git add frontend/static/js/app.js
git commit -m "feat: Generated Resume panel in job review modal"
```

---

### Task 9: Frontend — Tailor tab restore + saved-version confirmation

**Files:**
- Modify: `frontend/index.html` (banner container in tailor form)
- Modify: `frontend/static/js/app.js`

**Interfaces:**
- Consumes: `GET /jobs/{id}/resumes/latest`, `X-Resume-Version` header from `/export` (Tasks 5–6); globals `lastTailorJobId`, `lastTailorBlockIds`, `lastTailorVersion` (app.js:19–21); block checkboxes inside `#block-selector`; `#resume-preview-section` / `#resume-preview-text`; `#template-selector`.
- Produces: `loadSavedResumeInTailor(jobId)` (consumed by Task 8's panel).

- [ ] **Step 1: Add the banner container.** In `frontend/index.html`, inside the tailor form, directly after the `<select id="select-job" ...>` element's enclosing form-group div, add:

```html
                <div id="saved-resume-banner" class="result-box hidden"></div>
```

- [ ] **Step 2: Implement the restore flow.** In `frontend/static/js/app.js`:

Wire the check to job selection — find where `select-job` gets its change/init handling (or add one in the `DOMContentLoaded` listener):

```javascript
    document.getElementById('select-job').addEventListener('change', (e) => {
        checkSavedResume(parseInt(e.target.value, 10));
    });
```

Add the functions:

```javascript
// Saved-resume restore: a job that already has a generated resume offers to
// reload it so the user tweaks and re-exports instead of rebuilding.
async function checkSavedResume(jobId) {
    const banner = document.getElementById('saved-resume-banner');
    if (!banner) return;
    banner.classList.add('hidden');
    if (!jobId) return;
    try {
        const resp = await fetch(`${API_BASE}/jobs/${jobId}/resumes/latest`);
        if (!resp.ok) return; // 404 = nothing saved, stay hidden
        const saved = await resp.json();
        banner.innerHTML = `Saved resume <strong>v${saved.version}</strong> (${new Date(saved.created_at).toLocaleDateString()}) exists for this job.
            <button type="button" class="btn btn-secondary" onclick="loadSavedResumeInTailor(${jobId})">Load saved resume</button>`;
        banner.classList.remove('hidden');
    } catch (e) {
        console.error('Saved-resume check failed:', e);
    }
}

async function loadSavedResumeInTailor(jobId) {
    try {
        const resp = await fetch(`${API_BASE}/jobs/${jobId}/resumes/latest`);
        if (!resp.ok) {
            alert('No saved resume found for this job.');
            return;
        }
        const saved = await resp.json();

        // Switch to the Tailor tab and select the job
        document.querySelector('.tab-button[data-tab="tailor"]').click();
        const jobSelect = document.getElementById('select-job');
        jobSelect.value = String(jobId);

        // Restore block selection
        const wanted = new Set(saved.block_ids);
        document.querySelectorAll('#block-selector input[type="checkbox"]').forEach(cb => {
            cb.checked = wanted.has(parseInt(cb.value, 10));
        });

        // Restore template + export state so download buttons work immediately
        const templateSel = document.getElementById('template-selector');
        if (templateSel) templateSel.value = saved.template;
        const tailoredToggle = document.getElementById('tailored-export-toggle');
        if (tailoredToggle) tailoredToggle.checked = saved.tailored;
        lastTailorJobId = jobId;
        lastTailorBlockIds = saved.block_ids;
        lastTailorVersion = `v${saved.version}`;

        // Show the saved text in the preview pane
        document.getElementById('resume-preview-text').textContent = saved.resume_text;
        document.getElementById('resume-preview-section').classList.remove('hidden');

        if (saved.missing_block_ids.length) {
            alert(`Loaded v${saved.version}, but ${saved.missing_block_ids.length} block(s) used in it were deleted since (IDs: ${saved.missing_block_ids.join(', ')}). The saved text above is complete; the block selection loaded what still exists.`);
        }
        const modal = document.getElementById('job-review-modal');
        if (modal) modal.classList.add('hidden');
    } catch (error) {
        alert('Could not load saved resume: ' + error.message);
    }
}
```

If Task 8's temporary `loadSavedResumeInTailor` stub exists, delete it.

- [ ] **Step 3: Post-export confirmation.** In `downloadResumeAs(format)` (app.js:1705), after the blob download completes (after `URL.revokeObjectURL(url)`), add:

```javascript
        const savedVersion = response.headers.get('x-resume-version');
        if (savedVersion) {
            checkSavedResume(lastTailorJobId);
            const preview = document.getElementById('resume-preview-section');
            if (preview) {
                let note = document.getElementById('export-saved-note');
                if (!note) {
                    note = document.createElement('p');
                    note.id = 'export-saved-note';
                    preview.prepend(note);
                }
                note.textContent = `✔ Saved as v${savedVersion} on this job.`;
            }
        }
```

- [ ] **Step 4: Lint/sanity** — Run: `node --check frontend/static/js/app.js`
Expected: parses cleanly.

- [ ] **Step 5: Manual verification** — in the scratch-instance UI: select a job with a saved resume in the Tailor tab → banner appears; click Load → blocks re-check, preview fills, template restores, Download PDF works without re-tailoring; export → "Saved as vN" note appears; a job with no saves shows no banner.

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html frontend/static/js/app.js
git commit -m "feat: Tailor tab saved-resume restore + export confirmation"
```

---

### Task 10: Frontend — uploaded resumes list in Resume Intake

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/static/js/app.js`

**Interfaces:**
- Consumes: `GET /uploaded-resumes`, `GET /uploaded-resumes/{id}/download` (Task 7).

- [ ] **Step 1: Add the container.** In `frontend/index.html`, inside the Resume Intake tab (`<div id="resume" class="tab-content active">`), directly above the `<form id="upload-resume-form">` element, add:

```html
                <div id="uploaded-resumes-list"></div>
```

- [ ] **Step 2: Implement.** In `frontend/static/js/app.js`, add:

```javascript
async function loadUploadedResumes() {
    const container = document.getElementById('uploaded-resumes-list');
    if (!container) return;
    try {
        const resp = await fetch(`${API_BASE}/uploaded-resumes`);
        if (!resp.ok) return;
        const uploads = await resp.json();
        if (!uploads.length) {
            container.innerHTML = '';
            return;
        }
        container.innerHTML = `
            <h4>Previously uploaded resumes</h4>
            <ul class="job-review-list">${uploads.map(u =>
                `<li>${esc(u.filename)} — ${new Date(u.created_at).toLocaleDateString()}, ${u.block_count} block(s)
                 <a href="${API_BASE}/uploaded-resumes/${u.id}/download">download</a></li>`).join('')}
            </ul>`;
    } catch (e) {
        console.error('Failed to load uploaded resumes:', e);
    }
}
```

Call it on startup — in the `DOMContentLoaded` handler (or wherever `loadJobs()` is called on init, app.js:52), add `loadUploadedResumes();`. Also call it after a successful upload: in the upload-form success path (where `upload-result` is shown after `/parse-resume` + confirm succeed, ~app.js:306–370) add `loadUploadedResumes();`.

Thread `upload_id` through confirm: where the frontend calls `/parse-resume` (app.js:306), keep the returned `upload_id` in a module-scoped variable (`let lastUploadId = null;` next to the other globals) and include it in both `/confirm-resume-blocks` request bodies (app.js:326 and :539): `body: JSON.stringify({ blocks: ..., upload_id: lastUploadId })`.

- [ ] **Step 3: Lint/sanity** — Run: `node --check frontend/static/js/app.js`
Expected: parses cleanly.

- [ ] **Step 4: Manual verification** — upload a resume in the scratch UI; after confirm, the list shows the file with block count; the download link returns the original bytes; reload the page — the list persists.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/static/js/app.js
git commit -m "feat: uploaded-resumes list in Resume Intake"
```

---

### Task 11: Full verification, PR

**Files:** none new.

- [ ] **Step 1: Full suite + lint**

Run: `pytest && ruff check .`
Expected: all tests pass (379+ existing + new), no lint errors.

- [ ] **Step 2: End-to-end click-through** in the scratch instance: capture job → tailor → export PDF → export DOCX (same content: still one version, both formats) → change a block, export again (v2) → reload browser → Review capture shows v2 + history → Load in Tailor restores → Resume Intake lists the uploaded file.

- [ ] **Step 3: Push branch + open PR** (delegate to gh-worker): push `feat/job-resume-pairing`, open PR titled "Job + resume pairing: persist generated resumes with their job" referencing `specs/job-resume-pairing.md`; body summarizes the two save points, versioning semantics, and restore flow. CI `test` check must pass; user approves per master ruleset.

- [ ] **Step 4: After merge (user-driven):** deploy to staging (:3001) by restart for a click-through, then live (:3000). Tables self-create; no migration.
