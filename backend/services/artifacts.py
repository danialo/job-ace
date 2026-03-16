from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from slugify import slugify
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import models

settings = get_settings()


class ArtifactManager:
    def __init__(self, db: Session):
        self.db = db

    def ensure_job_dir(self, job_posting: models.JobPosting) -> Path:
        created = job_posting.created_at or datetime.now(timezone.utc)
        company = slugify(job_posting.company.name if job_posting.company else "unknown")
        title = slugify(job_posting.title or "role")
        location = slugify(job_posting.location or "remote")
        folder_name = f"{created.strftime('%Y%m%d')}__{company}__{title}__{location}__job{job_posting.id}"
        job_dir = settings.data_root / folder_name
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "raw").mkdir(exist_ok=True)
        (job_dir / "derived").mkdir(exist_ok=True)
        (job_dir / "submission").mkdir(exist_ok=True)
        return job_dir

    def write_text(self, job_posting: models.JobPosting, kind: str, relative_path: str, content: str) -> Path:
        job_dir = self.ensure_job_dir(job_posting)
        full_path = job_dir / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        self.register_path(job_posting, kind, full_path)
        return full_path

    def write_bytes(self, job_posting: models.JobPosting, kind: str, relative_path: str, content: bytes) -> Path:
        job_dir = self.ensure_job_dir(job_posting)
        full_path = job_dir / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        self.register_path(job_posting, kind, full_path)
        return full_path

    def register_path(self, job_posting: models.JobPosting, kind: str, path: Path) -> None:
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

        # Check if artifact already exists
        existing = self.db.query(models.Artifact).filter(
            models.Artifact.kind == kind,
            models.Artifact.path == str(path)
        ).first()

        if existing:
            # Update existing artifact
            existing.sha256 = sha256
            existing.size_bytes = path.stat().st_size
        else:
            # Create new artifact
            artifact = models.Artifact(
                job_posting_id=job_posting.id,
                application_id=job_posting.application.id if job_posting.application else None,
                kind=kind,
                path=str(path),
                sha256=sha256,
                size_bytes=path.stat().st_size,
            )
            self.db.add(artifact)

        self.db.flush()

    def get_artifact(self, job_posting: models.JobPosting, kind: str) -> Optional[models.Artifact]:
        for artifact in job_posting.artifacts:
            if artifact.kind == kind:
                return artifact
        return None
