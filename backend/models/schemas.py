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


class UpdateBlockResponse(BaseModel):
    id: int
    category: str
    tags: str
    text: str
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


class ConfirmResumeBlocksRequest(BaseModel):
    """Request to confirm and save parsed resume blocks."""
    blocks: List[ConfirmBlockData]


class ConfirmResumeBlocksResponse(BaseModel):
    """Response after confirming and saving blocks."""
    message: str
    blocks_saved: int
    block_ids: List[int]
