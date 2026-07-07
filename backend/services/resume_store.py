"""Resume Store Service.

Owns the pairing record between a job posting and the resumes generated for
it (versioned, format-merged) plus original uploaded resume files.
See specs/job-resume-pairing.md.
"""

from __future__ import annotations

import hashlib
import json
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
