from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import models
from backend.services.artifacts import ArtifactManager
from backend.services.compliance import run_compliance
from backend.services.llm import BaseLLMClient, get_llm_client
from backend.config import get_settings


# Only prose blocks get aligned to the job. Factual lists (skills, education,
# certifications, contact) are left verbatim — rewriting them adds no honest
# signal and risks cosmetic damage (stray bullets, reordered facts).
ALIGNABLE_CATEGORIES = {
    "summary",
    "professional summary",
    "career summary",
    "profile",
    "objective",
    "experience",
    "work experience",
    "work",
    "employment",
}


class TailorService:
    def __init__(self, db: Session, llm: BaseLLMClient | None = None):
        self.db = db
        self.artifacts = ArtifactManager(db)
        self.settings = get_settings()
        self.llm = llm or get_llm_client(self.settings, task="tailoring")

    def run(self, job_id: int, allowed_block_ids: List[int], resume_version: str) -> Dict:
        job_posting = self._get_job(job_id)
        jd_payload = self._load_jd(job_posting)
        blocks = self._load_blocks(allowed_block_ids)

        request_payload = {
            "jd": jd_payload,
            "allowed_blocks": blocks,
            "resume_version": resume_version,
        }
        self.artifacts.write_text(
            job_posting,
            "tailor_request",
            "derived/tailor_request.json",
            json.dumps(request_payload, ensure_ascii=False, indent=2),
        )

        result = self.llm.tailor_resume(jd_payload, blocks)
        self.artifacts.write_text(
            job_posting,
            "tailor_response",
            "derived/tailor_response.json",
            json.dumps(result, ensure_ascii=False, indent=2),
        )

        resume_body_md = result.get("resume_body_md", "")
        ats_text = result.get("resume_ats_text", "")

        resume_md_path = self.artifacts.write_text(
            job_posting,
            "resume_body_md",
            f"derived/resume_body_{resume_version}.md",
            resume_body_md,
        )
        ats_path = self.artifacts.write_text(
            job_posting,
            "resume_ats",
            f"derived/resume_ats_{resume_version}.txt",
            ats_text,
        )

        if job_posting.application:
            job_posting.application.resume_artifact_path = str(resume_md_path)
            self.db.flush()

        compliance = run_compliance(self.db, job_posting, blocks, result)

        # Produce + store a per-job tailored version of the blocks for export
        # (rewritten to the job, fabrication-gated). Never mutates the base blocks.
        tailored = self.generate_tailored_overrides(job_id, allowed_block_ids)

        response = {
            "resume_body_md": resume_body_md,
            "ats_text": ats_text,
            "coverage": result.get("coverage_table", []),
            "uncovered": result.get("uncovered_keywords", []),
            "diff": json.dumps(result.get("diff_instructions", []), ensure_ascii=False),
            "compliance_pass": compliance.ok,
            "tailored_block_count": len(tailored),
        }
        return response

    def generate_tailored_overrides(
        self, job_id: int, allowed_block_ids: List[int]
    ) -> Dict[int, str]:
        """Rewrite blocks to the job (no fabrication), compliance-gate, and persist for
        export. Returns {block_id: text}. If the rewrite trips the fabrication check, ALL
        overrides are dropped so export falls back to the candidate's honest base text."""
        job_posting = self._get_job(job_id)
        jd = self._load_jd(job_posting)
        blocks = self._load_blocks(allowed_block_ids)

        # Align only prose blocks; leave factual lists untouched.
        prose_blocks = [
            b for b in blocks
            if (b.get("category") or "").lower().strip() in ALIGNABLE_CATEGORIES
        ]

        rewrite = getattr(self.llm, "rewrite_blocks_for_job", None)
        overrides: Dict[int, str] = (
            rewrite(jd, prose_blocks) if rewrite and prose_blocks else {}
        )

        if overrides:
            tailored_text = "\n\n".join(overrides.get(b["id"], b["text"]) for b in blocks)
            try:
                check = self.llm.check_compliance(tailored_text, blocks, jd)
                if not check.ok:
                    overrides = {}
            except Exception:
                overrides = {}

        self.artifacts.write_text(
            job_posting,
            "tailored_blocks",
            "derived/tailored_blocks.json",
            json.dumps({str(k): v for k, v in overrides.items()}, ensure_ascii=False, indent=2),
        )
        self.db.flush()
        return overrides

    def _get_job(self, job_id: int) -> models.JobPosting:
        job_posting = self.db.get(models.JobPosting, job_id)
        if not job_posting:
            raise ValueError(f"Job posting {job_id} not found")
        return job_posting

    def _load_jd(self, job_posting: models.JobPosting) -> Dict:
        if not job_posting.jd_json_path:
            raise ValueError("Job description JSON missing")
        data = Path(job_posting.jd_json_path).read_text(encoding="utf-8")
        return json.loads(data)

    def _load_blocks(self, block_ids: List[int]) -> List[Dict]:
        if not block_ids:
            raise ValueError("No resume blocks supplied")
        stmt = select(models.ResumeBlock).where(models.ResumeBlock.id.in_(block_ids))
        blocks = self.db.scalars(stmt).all()
        if len(blocks) != len(block_ids):
            raise ValueError("One or more resume blocks missing")
        payload: List[Dict] = []
        for block in blocks:
            entry: Dict = {
                "id": block.id,
                "category": block.category,
                "tags": (block.tags or "").split(",") if block.tags else [],
                "text": block.text,
            }
            if block.job_title:
                entry["job_title"] = block.job_title
            if block.company:
                entry["company"] = block.company
            if block.start_date:
                entry["start_date"] = block.start_date
            if block.end_date:
                entry["end_date"] = block.end_date
            payload.append(entry)
        return payload
