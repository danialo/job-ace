from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List

import httpx
import structlog

from backend.config import get_settings

logger = structlog.get_logger()


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

    @classmethod
    def from_dict(cls, data: Dict) -> "JDExtraction":
        salary = data.get("salary_range", {}) or {}
        return cls(
            title=data.get("title"),
            company=data.get("company"),
            location=data.get("location"),
            employment_type=data.get("employment_type"),
            seniority=data.get("seniority"),
            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            must_haves=data.get("must_haves", []),
            nice_to_haves=data.get("nice_to_haves", []),
            screening_questions=data.get("screening_questions", []),
            apply_url=data.get("apply_url"),
            deadline=data.get("deadline"),
            portal_hint=data.get("portal_hint"),
        )


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def extract_job_json(self, text: str) -> JDExtraction:
        """Extract structured job data from raw text."""
        pass

    @abstractmethod
    def tailor_resume(self, jd: Dict, allowed_blocks: List[Dict]) -> Dict:
        """Generate a tailored resume from job description and resume blocks."""
        pass


class StubLLMClient(BaseLLMClient):
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
        must_haves = [
            line.replace("Must have", "").strip()
            for line in lines
            if line.lower().startswith("must")
        ]
        nice_to_haves = [
            line.replace("Nice to have", "").strip()
            for line in lines
            if line.lower().startswith("nice")
        ]
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
            hits = [
                block["id"]
                for block in allowed_blocks
                if keyword.lower() in block["text"].lower()
            ]
            if hits:
                coverage.append({"keyword": keyword, "support_block_ids": hits})
            else:
                uncovered.append(keyword)
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


class AnthropicLLMClient(BaseLLMClient):
    """Real LLM client using Anthropic's Claude API."""

    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    JD_EXTRACTION_PROMPT = """You are a job description parser. Extract structured information from the following job posting text.

Return a JSON object with these fields:
- title: Job title (string or null)
- company: Company name (string or null)
- location: Job location (string or null, e.g., "Remote", "San Francisco, CA", "Hybrid - NYC")
- employment_type: "full-time", "part-time", "contract", "internship", or null
- seniority: "entry", "mid", "senior", "staff", "principal", "director", "vp", "c-level", or null
- salary_range: object with "min" (int or null), "max" (int or null), "currency" (string or null)
- must_haves: array of required qualifications/skills (strings)
- nice_to_haves: array of preferred/bonus qualifications (strings)
- screening_questions: array of any application questions mentioned (strings)
- apply_url: direct application URL if found (string or null)
- deadline: application deadline if mentioned (string or null)
- portal_hint: ATS/portal name if identifiable (e.g., "greenhouse", "lever", "workday", or null)

Be thorough when extracting must_haves and nice_to_haves - include technical skills, years of experience, education requirements, certifications, and soft skills.

Respond with ONLY the JSON object, no markdown or explanation.

Job Posting:
{text}"""

    TAILOR_RESUME_PROMPT = """You are an expert resume writer helping tailor a resume for a specific job.

## Job Description
{jd_json}

## Available Resume Blocks
Each block has an ID, category, tags, and text content:
{blocks_json}

## Instructions
1. Analyze the job requirements (must_haves, nice_to_haves)
2. Select and order the resume blocks to best match the job
3. For each block, suggest specific edits to better align with the job's language and requirements
4. Generate a cohesive resume that maintains authenticity while emphasizing relevant experience

## Output Format
Return a JSON object with:
- resume_body_md: The complete tailored resume in Markdown format
- resume_ats_text: Plain text version optimized for ATS scanning (no formatting)
- coverage_table: Array of {{"keyword": string, "support_block_ids": [int, ...]}} showing which blocks support each keyword
- uncovered_keywords: Array of job requirements NOT covered by any block
- one_line_summary: A one-line summary of this candidate's fit for the role
- diff_instructions: Array of {{"block_id": int, "changes": string}} describing changes made to each block

Focus on:
- Mirroring the job posting's language/terminology
- Quantifying achievements where possible
- Highlighting the most relevant experience first
- Maintaining truthfulness - do not fabricate experience

Respond with ONLY the JSON object, no markdown or explanation."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = httpx.Client(timeout=120.0)

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        """Make a request to the Anthropic API."""
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "anthropic-version": self.API_VERSION,
        }

        messages = [{"role": "user", "content": prompt}]

        payload: Dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": messages,
        }

        if system:
            payload["system"] = system

        logger.debug("Calling Anthropic API", model=self.model, prompt_len=len(prompt))

        response = self._client.post(self.API_URL, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        content = data.get("content", [])
        if content and content[0].get("type") == "text":
            return content[0]["text"]

        raise ValueError(f"Unexpected API response format: {data}")

    def _parse_json_response(self, text: str) -> Dict:
        """Extract JSON from response, handling markdown code blocks."""
        # Try to find JSON in code blocks first
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        # Clean up and parse
        text = text.strip()
        return json.loads(text)

    def extract_job_json(self, text: str) -> JDExtraction:
        """Extract structured job data using Claude."""
        prompt = self.JD_EXTRACTION_PROMPT.format(text=text[:15000])  # Limit input size

        try:
            response = self._call_api(prompt)
            data = self._parse_json_response(response)
            logger.info("Extracted job data via Anthropic", title=data.get("title"))
            return JDExtraction.from_dict(data)
        except Exception as e:
            logger.error("LLM extraction failed, falling back to stub", error=str(e))
            # Fallback to stub on error
            return StubLLMClient().extract_job_json(text)

    def tailor_resume(self, jd: Dict, allowed_blocks: List[Dict]) -> Dict:
        """Generate a tailored resume using Claude."""
        jd_json = json.dumps(jd, indent=2, ensure_ascii=False)
        blocks_json = json.dumps(allowed_blocks, indent=2, ensure_ascii=False)

        prompt = self.TAILOR_RESUME_PROMPT.format(jd_json=jd_json, blocks_json=blocks_json)

        try:
            response = self._call_api(prompt)
            result = self._parse_json_response(response)
            logger.info("Tailored resume via Anthropic", one_line=result.get("one_line_summary"))
            return result
        except Exception as e:
            logger.error("LLM tailoring failed, falling back to stub", error=str(e))
            # Fallback to stub on error
            return StubLLMClient().tailor_resume(jd, allowed_blocks)

    def __del__(self):
        if hasattr(self, "_client"):
            self._client.close()


def get_llm_client() -> BaseLLMClient:
    """Factory function to get the configured LLM client.

    Returns AnthropicLLMClient if configured, otherwise StubLLMClient.
    """
    settings = get_settings()

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning(
                "Anthropic provider selected but no API key configured, using stub"
            )
            return StubLLMClient()

        return AnthropicLLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

    return StubLLMClient()
