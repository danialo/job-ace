from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import models
from backend.services.artifacts import ArtifactManager


class SubmissionLogger:
    def __init__(self, db: Session):
        self.db = db
        self.artifacts = ArtifactManager(db)

    def log(self, job_id: int, confirmation_id: str | None, confirmation_text: str | None, screenshot_path: str | None) -> models.Application:
        job_posting = self.db.get(models.JobPosting, job_id)
        if not job_posting:
            raise ValueError(f"Job posting {job_id} not found")
        if not job_posting.application:
            raise ValueError("Application record missing")

        application = job_posting.application
        application.status = "submitted"
        application.applied_at = datetime.now(timezone.utc)
        application.confirmation_id = confirmation_id
        application.confirmation_text = confirmation_text

        if screenshot_path:
            src = Path(screenshot_path)
            if src.exists():
                target = self.artifacts.ensure_job_dir(job_posting) / "submission" / src.name
                if src.resolve() != target.resolve():
                    target.write_bytes(src.read_bytes())
                application.confirmation_text = confirmation_text or src.name
                self.artifacts.register_path(job_posting, "submit_proof", target)
        self.db.flush()
        return application
