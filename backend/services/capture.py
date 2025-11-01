from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict

from sqlalchemy.orm import Session

from backend.browser.capture import capture_form
from backend.models import models
from backend.services.artifacts import ArtifactManager


class CaptureService:
    def __init__(self, db: Session):
        self.db = db
        self.artifacts = ArtifactManager(db)

    def run(self, job_id: int, headless: bool = True) -> Dict:
        job_posting = self.db.get(models.JobPosting, job_id)
        if not job_posting:
            raise ValueError(f"Job posting {job_id} not found")
        url = job_posting.apply_url or job_posting.url
        artifact_dir = self.artifacts.ensure_job_dir(job_posting)
        result = capture_form(url, artifact_dir, headless=headless)

        summary = {
            "job_id": job_posting.id,
            "apply_url": url,
            "schema_path": str(result.schema_path),
            "raw_html_path": str(result.raw_html_path),
            "screenshots": [str(p) for p in result.screenshots],
            "stage_count": result.stage_count,
        }
        return summary

