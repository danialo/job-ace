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


class ResumeBlock(BaseModel):
    """A single resume block/section."""
    category: str = Field(description="Block category: summary, experience, education, skills, projects, certifications, awards, or other")
    tags: List[str] = Field(default_factory=list, description="Relevant technology/skill tags extracted from content")
    content: str = Field(description="The actual text content of this block")


class ResumeParsingSchema(BaseModel):
    """Schema for parsing resume text into structured blocks."""
    name: str | None = Field(description="Candidate's full name")
    email: str | None = Field(description="Email address")
    phone: str | None = Field(description="Phone number")
    linkedin: str | None = Field(description="LinkedIn URL")
    github: str | None = Field(description="GitHub URL or other portfolio links")
    blocks: List[ResumeBlock] = Field(description="""Each distinct section/entry as a separate block.
    IMPORTANT:
    - Split each job/experience into its OWN block
    - Split each education entry into its OWN block
    - Each project should be its own block
    - Summary/profile is ONE block
    - Skills section is ONE block (or split by category if there are distinct groupings)""")


class ResumeSection(BaseModel):
    """A detected section in a resume."""
    name: str = Field(description="Human-readable section name (e.g., 'Professional Summary', 'Work Experience')")
    category: str = Field(description="Normalized category: summary, experience, education, skills, projects, certifications, awards, or other")
    start_char: int = Field(description="Character position where this section starts in the original text")
    end_char: int = Field(description="Character position where this section ends in the original text")
    estimated_tokens: int = Field(description="Rough estimate of tokens in this section (for planning API calls)")


class SectionDetectionSchema(BaseModel):
    """Schema for detecting resume sections."""
    sections: List[ResumeSection] = Field(description="""List of all sections found in the resume, in order.
    IMPORTANT:
    - Identify major sections like Summary, Experience, Education, Skills, Projects, etc.
    - Provide accurate character positions for boundaries
    - Estimate tokens to help avoid hitting limits in subsequent calls""")


class SectionParsingSchema(BaseModel):
    """Schema for parsing a single section into blocks."""
    blocks: List[ResumeBlock] = Field(description="""Blocks extracted from this section using VERBATIM text.
    CRITICAL RULES:
    - COPY EXACT TEXT from the resume - NO rewriting, summarizing, or paraphrasing
    - For experience: Each job should be a separate block with ORIGINAL job description text
    - For education: Each degree/institution should be a separate block with ORIGINAL education text
    - For projects: Each project should be a separate block with ORIGINAL project description
    - For summary/skills: Usually one block per section with ORIGINAL text
    - Extract relevant tags for filtering (companies, technologies, skills)
    - The content field must contain the EXACT text from the resume""")


class OpenAIClient:
    """OpenAI-powered LLM client for job extraction and resume tailoring."""

    # Reasoning models that don't support structured outputs or use different API patterns
    # Note: GPT-5 support TBD when released - may support structured outputs
    REASONING_MODELS = {"o1-mini", "o1-preview", "o1", "o3-mini", "o3"}

    # Models that support structured outputs (response_format parameter)
    STRUCTURED_OUTPUT_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-5"}  # gpt-5 assumed

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.is_reasoning_model = model in self.REASONING_MODELS

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

    def detect_sections(self, text: str) -> List[Dict[str, Any]]:
        """Detect sections in resume text (Stage 1 of multi-stage parsing).

        Uses fast model (GPT-4o-mini) to identify section boundaries.
        Returns list of sections with character positions for extraction.
        """
        prompt = f"""Analyze this resume and identify all major sections.

For each section, provide:
- The section name (e.g., "Professional Summary", "Work Experience")
- A normalized category (summary, experience, education, skills, projects, certifications, awards, or other)
- The exact character position where the section starts and ends
- An estimate of how many tokens are in this section

Resume text (total length: {len(text)} characters):
{text}

Return the sections in the order they appear in the resume."""

        # Use structured outputs with GPT-4o-mini for speed and cost efficiency
        completion = self.client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at analyzing resume structure and identifying sections."},
                {"role": "user", "content": prompt}
            ],
            response_format=SectionDetectionSchema,
        )

        parsed = completion.choices[0].message.parsed
        return [
            {
                "name": section.name,
                "category": section.category,
                "start_char": section.start_char,
                "end_char": section.end_char,
                "estimated_tokens": section.estimated_tokens,
            }
            for section in parsed.sections
        ]

    def parse_section(self, section_text: str, category: str, section_name: str) -> List[Dict[str, Any]]:
        """Parse a single section into blocks (Stage 2 of multi-stage parsing).

        Args:
            section_text: The text of this specific section
            category: The normalized category (experience, education, etc.)
            section_name: Human-readable section name for context

        Returns:
            List of blocks extracted from this section
        """
        # Different instructions based on category
        if category == "experience":
            instruction = "Split each job/position into its OWN separate block. COPY THE EXACT TEXT AS-IS from the resume. DO NOT rewrite, summarize, or modify the text in any way."
        elif category == "education":
            instruction = "Split each degree/institution into its OWN separate block. COPY THE EXACT TEXT AS-IS from the resume. DO NOT rewrite, summarize, or modify the text."
        elif category == "projects":
            instruction = "Split each project into its OWN separate block. COPY THE EXACT TEXT AS-IS from the resume. DO NOT rewrite or summarize."
        elif category == "skills":
            instruction = "Extract skill categories or the full skills section. COPY THE EXACT TEXT AS-IS. DO NOT reorganize or reformat. Keep the original structure."
        else:
            instruction = f"Split this {category} section into logical blocks. COPY THE EXACT TEXT AS-IS for each block. DO NOT modify the wording."

        prompt = f"""Extract structured blocks from this resume section by splitting on natural boundaries (each job, each degree, etc.).

CRITICAL: You must COPY THE EXACT ORIGINAL TEXT from the resume. DO NOT:
- Rewrite or paraphrase
- Summarize or shorten
- Add new information
- Reorganize or reformat
- Change any wording

Your job is ONLY to identify where to split the text into blocks. The content must be verbatim from the original resume.

Section: {section_name}
Category: {category}

Instructions: {instruction}

Section text:
{section_text}

For each block, provide:
- category: Use the category "{category}"
- tags: Extract relevant keywords (companies, technologies, skills) for filtering purposes
- content: THE EXACT VERBATIM TEXT FROM THE RESUME for this block (no modifications)"""

        # Use structured outputs with GPT-4o for quality
        completion = self.client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at identifying section boundaries in resumes and extracting verbatim text. You NEVER rewrite, summarize, or modify the original text. You only split text into blocks and copy it exactly as written."},
                {"role": "user", "content": prompt}
            ],
            response_format=SectionParsingSchema,
        )

        parsed = completion.choices[0].message.parsed
        return [
            {
                "category": block.category,
                "tags": block.tags,
                "content": block.content,
            }
            for block in parsed.blocks
        ]

    def parse_resume(self, text: str) -> Dict[str, Any]:
        """Parse resume text into structured blocks using OpenAI.

        Each job/experience entry becomes its own block for maximum flexibility.
        Works with both reasoning models (o1) and standard models (GPT-4o).
        """
        prompt = f"""Parse this resume into structured JSON blocks. Be extremely precise about splitting experience entries.

CRITICAL REQUIREMENTS:
1. Split EACH job/experience into its OWN separate block
2. Split EACH education entry into its OWN separate block
3. Each project should be its own block
4. Professional summary/profile is ONE block
5. Skills can be one block or split by category (technical vs soft skills, etc.)

For experience blocks, extract metadata:
- company: Company name
- title: Job title/role
- start_date: Start date (format: "YYYY" or "YYYY-MM")
- end_date: End date (format: "YYYY" or "YYYY-MM" or "Present")

Extract relevant technology tags for each block (programming languages, frameworks, tools, etc.).

Return JSON in this exact format:
{{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "phone number",
  "linkedin": "linkedin URL",
  "github": "github URL",
  "blocks": [
    {{
      "category": "summary|experience|education|skills|projects|certifications|awards|other",
      "tags": ["python", "aws", ...],
      "content": "The actual text content",
      "metadata": {{"company": "...", "title": "...", "start_date": "...", "end_date": "..."}}
    }}
  ]
}}

RESUME TEXT:
{text}"""

        if self.is_reasoning_model:
            # Reasoning models (o1): no system message, no temperature, no structured outputs
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content
            result = json.loads(content)
        else:
            # Standard models (GPT-4o): use structured outputs for reliability
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at parsing resumes into structured, reusable blocks for job applications."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format=ResumeParsingSchema,
            )
            parsed = completion.choices[0].message.parsed
            result = {
                "name": parsed.name,
                "email": parsed.email,
                "phone": parsed.phone,
                "linkedin": parsed.linkedin,
                "github": parsed.github,
                "blocks": [
                    {
                        "category": block.category,
                        "tags": block.tags,
                        "content": block.content,
                    }
                    for block in parsed.blocks
                ]
            }

        # Count blocks by category for summary
        category_counts = {}
        for block in result["blocks"]:
            category = block["category"]
            category_counts[category] = category_counts.get(category, 0) + 1

        return {
            "metadata": {
                "name": result.get("name"),
                "email": result.get("email"),
                "phone": result.get("phone"),
                "linkedin": result.get("linkedin"),
                "github": result.get("github"),
            },
            "blocks": result["blocks"],
            "parsing_summary": {
                "total_blocks": len(result["blocks"]),
                "blocks_by_category": category_counts,
                "model_used": self.model,
            }
        }

    def tailor_resume(self, jd: Dict, allowed_blocks: List[Dict]) -> Dict:
        """Tailor resume using OpenAI to analyze coverage and relevance.

        Uses reasoning models (o1/o3) for deep analysis, or GPT-4o/5 for speed.
        """
        resume_sections = [f"Block {block['id']}: {block['text'].strip()}" for block in allowed_blocks]
        resume_text = "\n\n".join(resume_sections)

        keywords = jd.get("must_haves", []) + jd.get("nice_to_haves", [])

        # Build comprehensive analysis prompt
        prompt = f"""You are an expert resume analyst and career coach. Analyze how well this resume matches the job requirements for precision and reliability.

JOB POSTING:
Title: {jd.get('title', 'Unknown')}
Company: {jd.get('company', 'Unknown')}
Location: {jd.get('location', 'Unknown')}

REQUIRED QUALIFICATIONS (must_haves):
{chr(10).join(f"- {req}" for req in jd.get('must_haves', []))}

PREFERRED QUALIFICATIONS (nice_to_haves):
{chr(10).join(f"- {pref}" for pref in jd.get('nice_to_haves', []))}

RESUME BLOCKS AVAILABLE:
{resume_text}

TASK:
Perform a detailed analysis:
1. For EACH requirement (must-have and nice-to-have), identify which resume block(s) provide evidence
2. Rate the strength of evidence (strong/moderate/weak/missing)
3. Identify gaps where requirements are not addressed
4. Suggest specific improvements or additions
5. Assess ATS keyword coverage and recommend optimizations
6. Provide an overall match score (0-100%)

Be extremely thorough and precise - this directly impacts job application success."""

        # Use appropriate API pattern based on model type
        if self.is_reasoning_model:
            # Reasoning models: no system message, no temperature
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
        else:
            # Standard models: system message + temperature control
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert resume analyst helping to optimize resumes for ATS systems and hiring managers. Provide precise, actionable analysis."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,  # Low temperature for consistency
            )

        analysis = response.choices[0].message.content

        # Calculate coverage (keyword matching)
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
            "model_used": self.model,
        }


def get_llm_client(settings: Settings, task: str = "extraction"):
    """Factory function to get the appropriate LLM client based on settings and task.

    Args:
        settings: Application settings
        task: "extraction" (job parsing), "resume_parsing" (resume upload), or "tailoring" (resume analysis)
    """
    # If OpenAI API key is set (from JOB_ACE_OPENAI_API_KEY or OPENAI_API_KEY env var)
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")

    # Select model based on task
    if task == "tailoring":
        model = settings.llm_tailoring_model
    elif task == "resume_parsing":
        model = settings.llm_resume_parsing_model
    else:  # extraction
        model = settings.llm_extraction_model

    if api_key and model != "stub-model":
        return OpenAIClient(api_key=api_key, model=model)
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

    def detect_sections(self, text: str) -> List[Dict[str, Any]]:
        """Stub implementation: Simple regex-based section detection."""
        sections = []
        lines = text.split('\n')

        # Common section headers
        section_patterns = [
            (r'(?i)^(professional\s+)?summary', 'summary'),
            (r'(?i)^(work\s+)?experience', 'experience'),
            (r'(?i)^education', 'education'),
            (r'(?i)^skills?', 'skills'),
            (r'(?i)^projects?', 'projects'),
            (r'(?i)^certifications?', 'certifications'),
            (r'(?i)^awards?', 'awards'),
        ]

        current_pos = 0
        for i, line in enumerate(lines):
            for pattern, category in section_patterns:
                if re.match(pattern, line.strip()):
                    # Estimate position
                    char_pos = sum(len(l) + 1 for l in lines[:i])  # +1 for newline
                    sections.append({
                        'name': line.strip(),
                        'category': category,
                        'start_char': char_pos,
                        'end_char': char_pos + 500,  # Rough estimate
                        'estimated_tokens': 100,
                    })
                    break

        # If no sections detected, treat whole text as one section
        if not sections:
            sections.append({
                'name': 'Resume Content',
                'category': 'other',
                'start_char': 0,
                'end_char': len(text),
                'estimated_tokens': len(text) // 4,
            })

        return sections

    def parse_section(self, section_text: str, category: str, section_name: str) -> List[Dict[str, Any]]:
        """Stub implementation: Simple text-based parsing."""
        # For stub, just create one block per section
        tags = []

        # Extract simple tags (words that look like technologies)
        tech_keywords = ['python', 'java', 'javascript', 'react', 'aws', 'docker', 'kubernetes',
                        'sql', 'nosql', 'git', 'linux', 'api', 'rest', 'graphql', 'typescript']

        text_lower = section_text.lower()
        for keyword in tech_keywords:
            if keyword in text_lower:
                tags.append(keyword)

        return [{
            'category': category,
            'tags': tags[:10],  # Limit to 10 tags
            'content': section_text.strip(),
        }]

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
