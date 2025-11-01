from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from sqlalchemy.orm import Session

from backend.models import models
from backend.services.artifacts import ArtifactManager


class PrefillPlanner:
    def __init__(self, db: Session):
        self.db = db
        self.artifacts = ArtifactManager(db)

    def build_plan(self, job_id: int) -> Dict:
        job_posting = self.db.get(models.JobPosting, job_id)
        if not job_posting:
            raise ValueError(f"Job posting {job_id} not found")
        apply_url = job_posting.apply_url or job_posting.url
        resume_uploads: List[Dict] = []
        if job_posting.application and job_posting.application.resume_artifact_path:
            resume_uploads.append(
                {
                    "selector": "input[type=file][name=resume]",
                    "path": job_posting.application.resume_artifact_path,
                }
            )
        plan = {
            "apply_url": apply_url,
            "fields": [],
            "uploads": resume_uploads,
            "confirmation_selector": "#confirmation",
            "artifact_dir": str(self.artifacts.ensure_job_dir(job_posting)),
        }
        self.artifacts.write_text(
            job_posting,
            "prefill_plan",
            "submission/prefill_plan.json",
            json.dumps(plan, ensure_ascii=False, indent=2),
        )
        return plan
