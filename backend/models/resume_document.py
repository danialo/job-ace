"""Canonical Resume Object Model.

Pydantic models representing a normalized, semantic resume document.
Exporters render from this model — they do not perform semantic normalization.

Aligned with JSON Resume conventions where applicable:
- summary (prose) + highlights (bullets) pattern
- ISO 8601 partial date subsets
- Grouped skills with name + keywords

See specs/resume-object-model.md for full design rationale.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

class PartialDate(BaseModel):
    """Structured date supporting year-only, year-month, or full dates."""
    year: int | None = None
    month: int | None = None
    day: int | None = None
    raw_text: str | None = None  # preserve original text (e.g., "September 2021")

    def display(self) -> str:
        """Render a human-readable date string."""
        if self.raw_text:
            return self.raw_text
        parts = []
        if self.month:
            import calendar
            parts.append(calendar.month_abbr[self.month])
        if self.year:
            parts.append(str(self.year))
        return " ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Provenance & Normalization
# ---------------------------------------------------------------------------

class SourceProvenance(BaseModel):
    """Tracks where an entry came from."""
    source_block_id: int | None = None
    source_section_hint: str | None = None
    source_text: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    confidence: float | None = None


class NormalizationEvent(BaseModel):
    """Records a single normalization transformation."""
    rule_id: str  # e.g., "bullet_continuation_join", "skills_pipe_parse"
    description: str
    before: str | None = None
    after: str | None = None
    severity: str = "info"  # "info" or "warning"


# ---------------------------------------------------------------------------
# Entry Content (discriminated union)
# ---------------------------------------------------------------------------

class BulletsContent(BaseModel):
    """Bullet-point content. Each bullet is a single logical string,
    continuation lines already joined."""
    type: Literal["bullets"] = "bullets"
    bullets: list[str]


class ProseContent(BaseModel):
    """Prose/paragraph content (summaries, profiles, cover text)."""
    type: Literal["prose"] = "prose"
    paragraphs: list[str]


class SkillsGroup(BaseModel):
    """A group of related skills with optional label and display hint."""
    label: str | None = None  # e.g., "Technical Proficiencies"
    items: list[str]
    display_style: str = "inline"  # advisory: "inline", "list", "chips"


class SkillsContent(BaseModel):
    """Skills grouped by category."""
    type: Literal["skills"] = "skills"
    groups: list[SkillsGroup]


class ItemsContent(BaseModel):
    """Simple list content (certifications, awards, honors)."""
    type: Literal["items"] = "items"
    items: list[str]


EntryContent = Annotated[
    Union[BulletsContent, ProseContent, SkillsContent, ItemsContent],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

class EntryKind(str, Enum):
    experience = "experience"
    prose = "prose"
    skills = "skills"
    list_items = "list"
    education = "education"
    project = "project"


class EntryHeader(BaseModel):
    """Structured header for experience, education, project entries."""
    title: str | None = None  # job title, degree, project name
    organization: str | None = None  # company, school
    location: str | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    is_current: bool = False


class Entry(BaseModel):
    """A single item within a section."""
    kind: EntryKind
    header: EntryHeader | None = None
    content: EntryContent
    source: SourceProvenance | None = None


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

class SectionCategory(str, Enum):
    summary = "summary"
    skills = "skills"
    experience = "experience"
    education = "education"
    certifications = "certifications"
    projects = "projects"
    awards = "awards"
    other = "other"


class Section(BaseModel):
    """A resume section containing ordered entries."""
    category: SectionCategory
    heading: str  # display heading (may differ from category)
    entries: list[Entry]
    order: int


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

class Basics(BaseModel):
    """Contact and identity information."""
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    headline: str | None = None


class DocumentMetadata(BaseModel):
    """Metadata about the document's creation and normalization."""
    source_filename: str | None = None
    extraction_method: str | None = None  # "llm", "stub", "manual"
    extraction_warnings: list[str] = Field(default_factory=list)
    normalization_events: list[NormalizationEvent] = Field(default_factory=list)
    generated_at: str | None = None


class ResumeDocument(BaseModel):
    """Canonical resume document. All exporters render from this model."""
    basics: Basics
    sections: list[Section] = Field(default_factory=list)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
