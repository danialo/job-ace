from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.browser.analyzer import BrowserCapture, JobPageAnalyzer
from backend.models import models
from backend.services.artifacts import ArtifactManager

logger = logging.getLogger(__name__)


class AnalysisService:
    """Capture a job page and derive structured signals for fit scoring."""

    def __init__(self, db: Session, analyzer: Optional[JobPageAnalyzer] = None) -> None:
        self.db = db
        self.artifacts = ArtifactManager(db)
        self.analyzer = analyzer or JobPageAnalyzer()

    def run(self, job_id: int, *, recapture: bool = False) -> Dict:
        job_posting = self.db.get(models.JobPosting, job_id)
        if not job_posting:
            raise ValueError(f"Job posting {job_id} not found")

        artifact_dir = self.artifacts.ensure_job_dir(job_posting)
        capture_needed = recapture or not job_posting.captured_html_path
        if capture_needed:
            capture = self.analyzer.capture(job_posting.url)
            html_path = self.artifacts.write_text(
                job_posting,
                kind="browser_capture_html",
                relative_path="raw/browser_capture.html",
                content=capture.html,
            )
            text_path = self.artifacts.write_text(
                job_posting,
                kind="browser_capture_text",
                relative_path="raw/browser_capture.txt",
                content=capture.text,
            )
            metadata_path = self.artifacts.write_text(
                job_posting,
                kind="browser_capture_meta",
                relative_path="raw/browser_capture_meta.json",
                content=json.dumps(capture.metadata, ensure_ascii=False, indent=2),
            )
            screenshot_path = None
            if capture.screenshot:
                screenshot_path = self.artifacts.write_bytes(
                    job_posting,
                    kind="browser_capture_png",
                    relative_path="raw/browser_capture.png",
                    content=capture.screenshot,
                )
            job_posting.captured_html_path = str(html_path)
            logger.info(
                "Captured job page",
                extra={
                    "job_id": job_posting.id,
                    "html_path": str(html_path),
                    "text_path": str(text_path),
                    "meta_path": str(metadata_path),
                    "screenshot_path": str(screenshot_path) if screenshot_path else None,
                },
            )
        else:
            html_path = job_posting.captured_html_path
            capture = None

        html_content = None
        if job_posting.captured_html_path:
            html_content = self._read_file(job_posting.captured_html_path)
        elif capture:
            html_content = capture.html

        text_content = None
        if html_content:
            text_content = self.analyzer._html_to_text(html_content)

        analysis_payload = self._build_analysis_payload(job_posting, html_content, text_content, capture)
        analysis_path = self.artifacts.write_text(
            job_posting,
            kind="analysis_summary",
            relative_path="derived/analysis_summary.json",
            content=json.dumps(analysis_payload, ensure_ascii=False, indent=2),
        )

        job_posting.analysis_json_path = str(analysis_path)
        job_posting.status = job_posting.status or "intake"
        self.db.flush()

        return {
            "job_id": job_posting.id,
            "analysis_path": str(analysis_path),
            "artifact_dir": str(artifact_dir),
            "sections": analysis_payload.get("sections", {}),
        }

    def _build_analysis_payload(
        self,
        job_posting: models.JobPosting,
        html_content: str | None,
        text_content: str | None,
        capture: Optional[BrowserCapture],
    ) -> Dict:
        sections: Dict[str, List[str]] = {}
        if html_content:
            sections = self._extract_sections(html_content)
        bullets = sections.get("bullets", [])

        sample_text = None
        if text_content:
            sample_text = text_content[:600]

        payload: Dict[str, object] = {
            "job_id": job_posting.id,
            "url": job_posting.url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "sections": sections,
            "bullet_count": len(bullets),
            "sample_text": sample_text,
        }
        if capture:
            payload["capture_metadata"] = capture.metadata
        return payload

    @staticmethod
    def _extract_sections(html: str) -> Dict[str, List[str]]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        headings = [tag.get_text(" ", strip=True) for tag in soup.find_all(["h1", "h2", "h3"])]
        paragraphs = [tag.get_text(" ", strip=True) for tag in soup.find_all("p") if tag.get_text(strip=True)]
        bullets = [tag.get_text(" ", strip=True) for tag in soup.find_all("li")]
        return {
            "headings": headings,
            "paragraphs": paragraphs,
            "bullets": bullets,
        }

    @staticmethod
    def _read_file(path: str) -> str:
        from pathlib import Path

        return Path(path).read_text(encoding="utf-8")
