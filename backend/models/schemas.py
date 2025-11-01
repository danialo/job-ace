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
