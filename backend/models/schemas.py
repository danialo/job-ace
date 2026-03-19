from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class IntakeRequest(BaseModel):
    url: str
    force: bool = False


class IntakeResponse(BaseModel):
    job_id: int
    artifact_dir: Path


class TailorRequest(BaseModel):
    job_id: int
    allowed_block_ids: List[int] = Field(default_factory=list)
    resume_version: str = "v1"


class CoverageItem(BaseModel):
    keyword: str
    support_block_ids: List[int]


class TailorResponse(BaseModel):
    resume_body_md: str
    ats_text: str
    coverage: List[CoverageItem]
    uncovered: List[str]
    diff: str
    compliance_pass: bool


class PrefillPlanRequest(BaseModel):
    job_id: int


class PrefillField(BaseModel):
    selector: str
    value: str
    type: str = "text"


class PrefillUpload(BaseModel):
    selector: str
    path: str


class PrefillPlanResponse(BaseModel):
    apply_url: str
    fields: List[PrefillField]
    uploads: List[PrefillUpload]
    confirmation_selector: Optional[str]
    artifact_dir: Path


class LogSubmitRequest(BaseModel):
    job_id: int
    confirmation_id: Optional[str] = None
    confirmation_text: Optional[str] = None
    screenshot_path: Optional[str] = None


class LogSubmitResponse(BaseModel):
    application_id: int
    status: str
    applied_at: datetime


class ArtifactPathResponse(BaseModel):
    path: Path


class UpdateBlockRequest(BaseModel):
    category: Optional[str] = None
    tags: Optional[str] = None
    text: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class UpdateBlockResponse(BaseModel):
    id: int
    category: str
    tags: str
    text: str
    job_title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    message: str = "Block updated successfully"


class DeleteBlockResponse(BaseModel):
    id: int
    message: str = "Block deleted successfully"


class ImproveBlockResponse(BaseModel):
    """Response from improving a block with LLM."""
    improved_text: str
    original_text: str


class ParsedBlock(BaseModel):
    """A parsed resume block ready for preview."""
    category: str
    tags: List[str]
    content: str
    job_title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ResumeSectionInfo(BaseModel):
    """Information about a detected resume section."""
    name: str
    category: str
    start_char: int
    end_char: int
    estimated_tokens: int


class ParseResumeResponse(BaseModel):
    """Response from parsing a resume (preview, not saved yet)."""
    blocks: List[ParsedBlock]
    metadata: dict
    sections: Optional[List[ResumeSectionInfo]] = None
    parsing_summary: Optional[dict] = None
    original_text: str = ""  # Original resume text before parsing


class ConfirmBlockData(BaseModel):
    """A block to be confirmed and saved to database."""
    category: str
    tags: List[str]
    content: str
    job_title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ConfirmResumeBlocksRequest(BaseModel):
    """Request to confirm and save parsed resume blocks."""
    blocks: List[ConfirmBlockData]


class ConfirmResumeBlocksResponse(BaseModel):
    """Response after confirming and saving blocks."""
    message: str
    blocks_saved: int
    block_ids: List[int]


class ExportRequest(BaseModel):
    """Request to export a resume as PDF or DOCX."""
    job_id: int
    block_ids: List[int]
    template: str = "classic"
    format: str = "pdf"  # "pdf" or "docx"
    resume_version: str = "v1"


class TemplateInfo(BaseModel):
    """Information about an available resume template."""
    id: str
    name: str
    description: str


# ============================================================================
# Job Inspection View Schemas
# ============================================================================


class JobSummary(BaseModel):
    """Summary fields for job list view."""
    id: int
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    url: str
    portal_hint: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    captured_at: Optional[datetime] = None
    extraction_quality: Optional[str] = None  # "rich" | "minimal" | "thin"


class ExtractedRequirements(BaseModel):
    """Extracted job requirements and qualifications."""
    must_haves: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)
    screening_questions: List[str] = Field(default_factory=list)
    employment_type: Optional[str] = None
    seniority: Optional[str] = None
    deadline: Optional[str] = None


class JobProvenance(BaseModel):
    """Provenance and debug information for extraction."""
    source_url: str
    apply_url: Optional[str] = None
    portal_hint: Optional[str] = None
    captured_at: Optional[datetime] = None
    artifact_dir: Optional[str] = None
    jd_json_path: Optional[str] = None
    raw_text_available: bool = False
    raw_text_chars: int = 0


class ExtractionQuality(BaseModel):
    """Quality metrics for job extraction."""
    must_haves_count: int = 0
    nice_to_haves_count: int = 0
    screening_questions_count: int = 0
    has_salary: bool = False
    has_location: bool = False
    has_employment_type: bool = False
    has_seniority: bool = False
    quality_tier: str = "unknown"  # "rich" | "minimal" | "thin"


class JobDetailResponse(BaseModel):
    """Full job detail response for inspection view."""
    job: JobSummary
    extracted: ExtractedRequirements
    provenance: JobProvenance
    quality: ExtractionQuality
