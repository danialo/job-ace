from __future__ import annotations

import json
import re
import structlog
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set

from sqlalchemy.orm import Session

from backend.models import models
from backend.services.artifacts import ArtifactManager
from backend.services.llm import get_llm_client, ComplianceCheck, BaseLLMClient, StubLLMClient

logger = structlog.get_logger()


@dataclass
class ComplianceResult:
    ok: bool
    extraneous_tokens: List[str]
    blocked: bool
    notes: str
    # LLM-powered fields (optional, populated when LLM is used)
    fabrications: List[Dict] | None = None
    style_changes: List[str] | None = None
    confidence: float | None = None
    method: str = "token"  # "token" or "llm"

    def to_json(self) -> str:
        payload = {
            "ok": self.ok,
            "extraneous_tokens": self.extraneous_tokens,
            "blocked": self.blocked,
            "notes": self.notes,
            "method": self.method,
        }
        if self.fabrications is not None:
            payload["fabrications"] = self.fabrications
        if self.style_changes is not None:
            payload["style_changes"] = self.style_changes
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return json.dumps(payload, ensure_ascii=False, indent=2)


def run_compliance(
    db: Session,
    job_posting: models.JobPosting,
    allowed_blocks: List[Dict],
    tailor_output: Dict,
    use_llm: bool = True,
    llm_client: BaseLLMClient | None = None,
) -> ComplianceResult:
    """Run compliance check on tailored resume.

    Args:
        db: Database session
        job_posting: The job posting being applied to
        allowed_blocks: Source resume blocks (ground truth)
        tailor_output: Output from tailor_resume (contains resume_body_md, resume_ats_text)
        use_llm: Whether to use LLM for intelligent compliance checking
        llm_client: Optional LLM client (uses factory default if not provided)

    Returns:
        ComplianceResult with ok/blocked status and details
    """
    resume_text = " ".join([
        tailor_output.get("resume_body_md", ""),
        tailor_output.get("resume_ats_text", ""),
    ])

    # Try LLM-powered compliance if enabled
    if use_llm:
        client = llm_client or get_llm_client()

        # Only use LLM if we have a real provider (not stub)
        if not isinstance(client, StubLLMClient):
            try:
                # Build job context for the LLM
                job_context = {
                    "title": job_posting.title,
                    "company": job_posting.company,
                    "url": job_posting.url,
                }

                llm_result = client.check_compliance(
                    resume_text=resume_text,
                    source_blocks=allowed_blocks,
                    job_context=job_context,
                )

                result = ComplianceResult(
                    ok=llm_result.ok,
                    extraneous_tokens=[],  # LLM doesn't use token matching
                    blocked=not llm_result.ok,
                    notes=llm_result.notes,
                    fabrications=llm_result.fabrications,
                    style_changes=llm_result.style_changes,
                    confidence=llm_result.confidence,
                    method="llm",
                )

                logger.info(
                    "LLM compliance check completed",
                    job_id=job_posting.id,
                    ok=result.ok,
                    fabrication_count=len(llm_result.fabrications),
                )

                _save_result(db, job_posting, result)
                return result

            except Exception as e:
                logger.warning(
                    "LLM compliance check failed, falling back to token method",
                    error=str(e),
                )

    # Fallback: token-based compliance (legacy method)
    result = _run_token_compliance(allowed_blocks, resume_text)
    _save_result(db, job_posting, result)
    return result


def _run_token_compliance(allowed_blocks: List[Dict], resume_text: str) -> ComplianceResult:
    """Original token-based compliance checking (fallback)."""
    whitelist = _build_whitelist(allowed_blocks)
    tokens = set(_tokenize(resume_text))
    extraneous = sorted(tok for tok in tokens if tok not in whitelist)
    blocked = bool(extraneous)

    return ComplianceResult(
        ok=not blocked,
        extraneous_tokens=extraneous,
        blocked=blocked,
        notes="Token-based check (legacy)" if blocked else "",
        method="token",
    )


def _save_result(
    db: Session, job_posting: models.JobPosting, result: ComplianceResult
) -> None:
    """Persist compliance result to artifacts."""
    artifact_mgr = ArtifactManager(db)
    artifact_mgr.write_text(
        job_posting,
        kind="compliance",
        relative_path="derived/compliance.json",
        content=result.to_json(),
    )

    report_path = artifact_mgr.ensure_job_dir(job_posting) / "derived" / "compliance.json"
    if job_posting.application:
        job_posting.application.compliance_report_path = str(report_path)
    db.flush()


def _build_whitelist(blocks: Iterable[Dict]) -> Set[str]:
    whitelist: Set[str] = set()
    for block in blocks:
        whitelist.update(_tokenize(block.get("text", "")))
    return whitelist


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9#+]+", text)]
