from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set

from sqlalchemy.orm import Session

from backend.models import models
from backend.services.artifacts import ArtifactManager


@dataclass
class ComplianceResult:
    ok: bool
    extraneous_tokens: List[str]
    blocked: bool
    notes: str

    def to_json(self) -> str:
        payload = {
            "ok": self.ok,
            "extraneous_tokens": self.extraneous_tokens,
            "blocked": self.blocked,
            "notes": self.notes,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


def run_compliance(
    db: Session,
    job_posting: models.JobPosting,
    allowed_blocks: List[Dict],
    tailor_output: Dict,
) -> ComplianceResult:
    whitelist = _build_whitelist(allowed_blocks)
    resume_text = " ".join([tailor_output.get("resume_body_md", ""), tailor_output.get("resume_ats_text", "")])
    tokens = set(_tokenize(resume_text))
    extraneous = sorted(tok for tok in tokens if tok not in whitelist)
    blocked = bool(extraneous)
    result = ComplianceResult(ok=not blocked, extraneous_tokens=extraneous, blocked=blocked, notes="")

    artifact_mgr = ArtifactManager(db)
    artifact_mgr.write_text(
        job_posting,
        kind="compliance",
        relative_path="derived/compliance.json",
        content=result.to_json(),
    )

    report_path = artifact_mgr.ensure_job_dir(job_posting) / "derived" / "compliance.json"
    job_posting.application.compliance_report_path = str(report_path) if job_posting.application else None
    db.flush()
    return result


def _build_whitelist(blocks: Iterable[Dict]) -> Set[str]:
    whitelist: Set[str] = set()
    for block in blocks:
        whitelist.update(_tokenize(block.get("text", "")))
    return whitelist


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9#+]+", text)]
