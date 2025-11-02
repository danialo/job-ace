from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from openai import OpenAI
from pydantic import BaseModel, Field

from backend.config import Settings


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


# Pydantic models for OpenAI structured outputs
class JobExtractionSchema(BaseModel):
    """Schema for extracting structured job posting data."""
    title: str | None = Field(description="Job title/position name")
    company: str | None = Field(description="Company or organization name")
    location: str | None = Field(description="Job location (city, state, country)")
    employment_type: str | None = Field(description="Employment type (Full-time, Part-time, Contract, etc.)")
    seniority: str | None = Field(description="Seniority level (Entry, Mid, Senior, Lead, etc.)")
    salary_min: int | None = Field(description="Minimum salary (extract number only)")
    salary_max: int | None = Field(description="Maximum salary (extract number only)")
    must_haves: List[str] = Field(default_factory=list, description="Required skills, qualifications, or experience")
    nice_to_haves: List[str] = Field(default_factory=list, description="Preferred/desired skills or qualifications")
    screening_questions: List[str] = Field(default_factory=list, description="Application screening questions")
    apply_url: str | None = Field(description="URL to apply for the job")
    deadline: str | None = Field(description="Application deadline")
    portal_hint: str | None = Field(description="Hints about application portal/process")


class ResumeAnalysisSchema(BaseModel):
    """Schema for resume tailoring analysis."""
    coverage: List[Dict[str, Any]] = Field(description="Keywords covered by resume blocks")
    uncovered: List[str] = Field(description="Keywords not covered in resume")
    suggestions: List[str] = Field(description="Suggestions for improving coverage")
    relevance_score: float = Field(description="Overall relevance score (0-1)")


class OpenAIClient:
    """OpenAI-powered LLM client for job extraction and resume tailoring."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def extract_job_json(self, text: str) -> JDExtraction:
        """Extract structured job data using OpenAI with structured outputs."""
        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert at extracting structured information from job postings.
Extract all relevant information accurately. For must_haves, focus on required qualifications,
years of experience, specific technologies, and hard requirements. For nice_to_haves,
extract preferred qualifications and bonus skills."""
                },
                {
                    "role": "user",
                    "content": f"Extract structured data from this job posting:\n\n{text}"
                }
            ],
            response_format=JobExtractionSchema,
        )

        result = completion.choices[0].message.parsed

        return JDExtraction(
            title=result.title,
            company=result.company,
            location=result.location,
            employment_type=result.employment_type,
            seniority=result.seniority,
            salary_min=result.salary_min,
            salary_max=result.salary_max,
            must_haves=result.must_haves,
            nice_to_haves=result.nice_to_haves,
            screening_questions=result.screening_questions,
            apply_url=result.apply_url,
            deadline=result.deadline,
            portal_hint=result.portal_hint,
        )

    def tailor_resume(self, jd: Dict, allowed_blocks: List[Dict]) -> Dict:
        """Tailor resume using OpenAI to analyze coverage and relevance."""
        resume_sections = [f"Block {block['id']}: {block['text'].strip()}" for block in allowed_blocks]
        resume_text = "\n\n".join(resume_sections)

        keywords = jd.get("must_haves", []) + jd.get("nice_to_haves", [])

        # Use OpenAI to analyze coverage
        prompt = f"""Analyze how well this resume covers the job requirements.

Job Title: {jd.get('title', 'Unknown')}

Required Skills (must_haves): {', '.join(jd.get('must_haves', []))}
Preferred Skills (nice_to_haves): {', '.join(jd.get('nice_to_haves', []))}

Resume Content:
{resume_text}

For each keyword, determine:
1. Which resume blocks (by ID) support that keyword
2. Whether the keyword is adequately covered
3. Suggestions for improving coverage
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert resume analyst helping to optimize resumes for ATS systems."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
        )

        analysis = response.choices[0].message.content

        # Simple coverage calculation (improved from stub)
        coverage = []
        uncovered = []
        for keyword in keywords:
            hits = [block["id"] for block in allowed_blocks if keyword.lower() in block["text"].lower()]
            if hits:
                coverage.append({"keyword": keyword, "support_block_ids": hits})
            else:
                uncovered.append(keyword)

        # Build resume text
        resume_body_md = "\n\n".join([block["text"].strip() for block in allowed_blocks])
        ats_text = "\n".join([block["text"].strip() for block in allowed_blocks])

        return {
            "resume_body_md": resume_body_md,
            "resume_ats_text": ats_text,
            "coverage_table": coverage,
            "uncovered_keywords": uncovered,
            "one_line_summary": f"Resume tailored for {jd.get('title', 'position')} at {jd.get('company', 'company')}",
            "diff_instructions": [
                {"block_id": block["id"], "changes": "included"} for block in allowed_blocks
            ],
            "ai_analysis": analysis,
        }


def get_llm_client(settings: Settings):
    """Factory function to get the appropriate LLM client based on settings."""
    # If OpenAI API key is set (from JOB_ACE_OPENAI_API_KEY or OPENAI_API_KEY env var)
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")

    if api_key and settings.llm_model != "stub-model":
        return OpenAIClient(api_key=api_key, model=settings.llm_model)
    else:
        return StubLLMClient()


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
