from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class JDExtraction:
    title: str | None
    company: str | None
    location: str | None
    employment_type: str | None
    seniority: str | None
    salary_min: int | None
    salary_max: int | None
    must_haves: List[str]
    nice_to_haves: List[str]
    screening_questions: List[str]
    apply_url: str | None
    deadline: str | None
    portal_hint: str | None

    def to_json(self) -> str:
        payload = {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "employment_type": self.employment_type,
            "seniority": self.seniority,
            "salary_range": {
                "min": self.salary_min,
                "max": self.salary_max,
                "currency": None,
            },
            "must_haves": self.must_haves,
            "nice_to_haves": self.nice_to_haves,
            "screening_questions": self.screening_questions,
            "apply_url": self.apply_url,
            "deadline": self.deadline,
            "portal_hint": self.portal_hint,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class StubLLMClient:
    """Deterministic heuristics for local development and tests."""

    TITLE_RE = re.compile(r"(?i)title[:\s]+(?P<value>.+)")
    COMPANY_RE = re.compile(r"(?i)company[:\s]+(?P<value>.+)")
    LOCATION_RE = re.compile(r"(?i)location[:\s]+(?P<value>.+)")

    def extract_job_json(self, text: str) -> JDExtraction:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        first_line = lines[0] if lines else None
        title = self._extract(self.TITLE_RE, lines) or (first_line if first_line else None)
        company = self._extract(self.COMPANY_RE, lines)
        location = self._extract(self.LOCATION_RE, lines)
        must_haves = [line.replace("Must have", "").strip() for line in lines if line.lower().startswith("must")]
        nice_to_haves = [line.replace("Nice to have", "").strip() for line in lines if line.lower().startswith("nice")]
        screening = [line for line in lines if line.endswith("?")]
        apply_url = self._find_url(lines)
        return JDExtraction(
            title=title,
            company=company,
            location=location,
            employment_type=None,
            seniority=None,
            salary_min=None,
            salary_max=None,
            must_haves=must_haves,
            nice_to_haves=nice_to_haves,
            screening_questions=screening,
            apply_url=apply_url,
            deadline=None,
            portal_hint=None,
        )

    def tailor_resume(self, jd: Dict, allowed_blocks: List[Dict]) -> Dict:
        resume_sections = [block["text"].strip() for block in allowed_blocks]
        resume_body_md = "\n\n".join(resume_sections)
        ats_text = "\n".join(resume_sections)
        keywords = jd.get("must_haves", []) + jd.get("nice_to_haves", [])
        coverage = []
        uncovered = []
        for keyword in keywords:
            hits = [block["id"] for block in allowed_blocks if keyword.lower() in block["text"].lower()]
            if hits:
                coverage.append({"keyword": keyword, "support_block_ids": hits})
            else:
                uncovered.append(keyword)
        diff = "\n".join(f"Block {block['id']} kept" for block in allowed_blocks)
        return {
            "resume_body_md": resume_body_md,
            "resume_ats_text": ats_text,
            "coverage_table": coverage,
            "uncovered_keywords": uncovered,
            "one_line_summary": jd.get("title") or "Tailored resume",
            "diff_instructions": [
                {"block_id": block["id"], "changes": "reordered"} for block in allowed_blocks
            ],
        }

    @staticmethod
    def _extract(pattern: re.Pattern, lines: List[str]) -> str | None:
        for line in lines:
            match = pattern.search(line)
            if match:
                return match.group("value").strip()
        return None

    @staticmethod
    def _find_url(lines: List[str]) -> str | None:
        for line in lines:
            match = re.search(r"https?://\S+", line)
            if match:
                return match.group(0)
        return None
