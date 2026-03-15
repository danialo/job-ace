"""Resume Normalization Service.

Converts raw resume blocks (from DB) into a canonical ResumeDocument.
Handles continuation-line joining, skills parsing, date extraction,
and PDF artifact cleanup.

This is a standalone module — not inside ExportService.
Normalization is independently testable and feeds every renderer
the same canonical object.

See specs/resume-object-model.md for design rationale.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import models
from backend.models.resume_document import (
    Basics,
    BulletsContent,
    DocumentMetadata,
    Entry,
    EntryHeader,
    EntryKind,
    ItemsContent,
    NormalizationEvent,
    PartialDate,
    ProseContent,
    ResumeDocument,
    Section,
    SectionCategory,
    SkillsContent,
    SkillsGroup,
    SourceProvenance,
)

# Bullet characters recognized as list markers
_BULLET_RE = re.compile(r"^[-•●*►▪▸]\s*(.+)$")

# Pipe-delimited skills: | Python | Bash | JSON |
_PIPE_SKILLS_RE = re.compile(r"^\|?\s*([^|]+(?:\|[^|]+)+)\s*\|?\s*$")

# Month names for date parsing
_MONTH_MAP = {
    name.lower(): i
    for i, name in enumerate(
        [
            "",
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ]
    )
    if name
}
_MONTH_ABBR_MAP = {
    name.lower(): i
    for i, name in enumerate(
        [
            "",
            "jan", "feb", "mar", "apr", "may", "jun",
            "jul", "aug", "sep", "oct", "nov", "dec",
        ]
    )
    if name
}

# Section ordering (lower = earlier in resume)
_SECTION_ORDER = {
    SectionCategory.summary: 0,
    SectionCategory.skills: 1,
    SectionCategory.experience: 2,
    SectionCategory.education: 3,
    SectionCategory.projects: 4,
    SectionCategory.certifications: 5,
    SectionCategory.awards: 6,
    SectionCategory.other: 7,
}

_HEADING_MAP = {
    SectionCategory.summary: "Professional Summary",
    SectionCategory.skills: "Skills",
    SectionCategory.experience: "Experience",
    SectionCategory.education: "Education",
    SectionCategory.projects: "Projects",
    SectionCategory.certifications: "Certifications",
    SectionCategory.awards: "Awards",
    SectionCategory.other: "Additional",
}

# PDF extraction artifact patterns
_ARTIFACT_PATTERNS = [
    # Space before hyphen: "customer -ready" → "customer-ready"
    (re.compile(r"(\w) -(\w)"), r"\1-\2", "space_before_hyphen"),
    # Split word with space: "Pr esent" → "Present" (conservative: only known cases)
    (re.compile(r"\bPr esent\b"), "Present", "split_word_present"),
]


class ResumeNormalizer:
    """Converts raw resume blocks into a canonical ResumeDocument."""

    def __init__(self, db: Session):
        self.db = db
        self._events: List[NormalizationEvent] = []

    def normalize(self, block_ids: List[int]) -> ResumeDocument:
        """Load blocks from DB and produce a normalized ResumeDocument."""
        if not block_ids:
            raise ValueError("No block IDs provided")

        stmt = select(models.ResumeBlock).where(models.ResumeBlock.id.in_(block_ids))
        blocks = list(self.db.scalars(stmt).all())
        if not blocks:
            raise ValueError("No blocks found for the given IDs")

        self._events = []
        basics = Basics(name="")
        sections_map: Dict[SectionCategory, List[Entry]] = {}
        headings: Dict[SectionCategory, str] = {}

        for block in blocks:
            cat = self._classify_category(block.category)

            if cat == SectionCategory.summary and block.category == "contact":
                # Contact blocks feed into basics
                basics = self._parse_basics(block.text, basics)
                continue

            entry = self._normalize_block(block, cat)
            sections_map.setdefault(cat, []).append(entry)

            # Use original section heading if available
            if cat not in headings and block.category:
                headings[cat] = block.category.replace("_", " ").title()

        # Build ordered sections
        sections = []
        for cat in sorted(sections_map.keys(), key=lambda c: _SECTION_ORDER.get(c, 99)):
            heading = headings.get(cat, _HEADING_MAP.get(cat, cat.value.title()))
            sections.append(
                Section(
                    category=cat,
                    heading=heading,
                    entries=sections_map[cat],
                    order=_SECTION_ORDER.get(cat, 99),
                )
            )

        return ResumeDocument(
            basics=basics,
            sections=sections,
            metadata=DocumentMetadata(
                extraction_method="database",
                normalization_events=list(self._events),
                generated_at=datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _classify_category(self, raw_category: str | None) -> SectionCategory:
        """Map raw block category string to SectionCategory enum."""
        if not raw_category:
            return SectionCategory.other
        normalized = raw_category.lower().strip()

        mapping = {
            "summary": SectionCategory.summary,
            "professional summary": SectionCategory.summary,
            "career summary": SectionCategory.summary,
            "profile": SectionCategory.summary,
            "objective": SectionCategory.summary,
            "contact": SectionCategory.summary,  # handled specially upstream
            "experience": SectionCategory.experience,
            "work experience": SectionCategory.experience,
            "work": SectionCategory.experience,
            "employment": SectionCategory.experience,
            "education": SectionCategory.education,
            "skills": SectionCategory.skills,
            "key skills": SectionCategory.skills,
            "technical skills": SectionCategory.skills,
            "technical proficiencies": SectionCategory.skills,
            "certifications": SectionCategory.certifications,
            "certificates": SectionCategory.certifications,
            "projects": SectionCategory.projects,
            "awards": SectionCategory.awards,
            "recognitions": SectionCategory.awards,
            "honors": SectionCategory.awards,
        }

        return mapping.get(normalized, SectionCategory.other)

    def _normalize_block(self, block: models.ResumeBlock, cat: SectionCategory) -> Entry:
        """Normalize a single block into an Entry based on its category."""
        source = SourceProvenance(
            source_block_id=block.id,
            source_text=block.text,
        )

        text = self._clean_artifacts(block.text)

        # Strip leading section heading from text if it matches the category
        text = self._strip_section_heading(text, cat)

        # Build header for structured entries
        header = None
        if cat in (SectionCategory.experience, SectionCategory.education, SectionCategory.projects):
            header = EntryHeader(
                title=block.job_title,
                organization=block.company,
                start_date=self._parse_date(block.start_date),
                end_date=self._parse_date(block.end_date),
                is_current=self._is_current(block.end_date),
            )
            # Strip the header line from text if it duplicates structured metadata
            text = self._strip_header_line(text, block)

        # Route to appropriate content type
        if cat == SectionCategory.summary:
            content = self._parse_prose(text)
            kind = EntryKind.prose
        elif cat == SectionCategory.skills:
            content = self._parse_skills(text)
            kind = EntryKind.skills
        elif cat in (SectionCategory.certifications, SectionCategory.awards):
            content = self._parse_items(text)
            kind = EntryKind.list_items
        elif cat in (SectionCategory.experience, SectionCategory.projects):
            content = self._parse_bullets(text)
            kind = EntryKind.experience if cat == SectionCategory.experience else EntryKind.project
        elif cat == SectionCategory.education:
            content = self._parse_bullets_or_prose(text)
            kind = EntryKind.education
        else:
            content = self._parse_bullets_or_prose(text)
            kind = EntryKind.prose

        return Entry(kind=kind, header=header, content=content, source=source)

    # -------------------------------------------------------------------
    # Content parsers
    # -------------------------------------------------------------------

    def _parse_bullets(self, text: str) -> BulletsContent:
        """Parse text into logical bullets with continuation-line joining."""
        bullets = self._extract_bullets(text)
        if not bullets:
            # Fallback: treat each non-empty line as a bullet
            bullets = [line.strip() for line in text.splitlines() if line.strip()]
        return BulletsContent(bullets=bullets)

    def _parse_prose(self, text: str) -> ProseContent:
        """Parse text as prose paragraphs."""
        paragraphs = []
        current = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
            else:
                current.append(stripped)
        if current:
            paragraphs.append(" ".join(current))
        return ProseContent(paragraphs=paragraphs)

    def _parse_skills(self, text: str) -> SkillsContent:
        """Parse skills text into grouped SkillsContent."""
        groups: List[SkillsGroup] = []
        current_label: str | None = None
        current_items: List[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # Check for pipe-delimited skills line (at least one | separator)
            if "|" in stripped:
                items = [s.strip().rstrip("|").strip() for s in stripped.split("|") if s.strip() and s.strip() != "|"]
                items = [i for i in items if i]  # remove empties after cleanup
                if items:
                    # If there's a pending group, save it
                    if current_items:
                        groups.append(SkillsGroup(label=current_label, items=current_items, display_style="inline"))
                        current_items = []
                        current_label = None
                    groups.append(SkillsGroup(label=current_label, items=items, display_style="inline"))
                    current_label = None
                    continue

            # Check if this is a label line (e.g., "KEY SKILLS", "TECHNICAL PROFICIENCIES")
            if stripped.isupper() or stripped.endswith(":"):
                if current_items:
                    groups.append(SkillsGroup(label=current_label, items=current_items, display_style="inline"))
                    current_items = []
                current_label = stripped.rstrip(":").strip().title()
                continue

            # Comma-separated skills
            if "," in stripped:
                items = [s.strip() for s in stripped.split(",") if s.strip()]
                current_items.extend(items)
                continue

            # Bullet-prefixed skill
            bullet_match = _BULLET_RE.match(stripped)
            if bullet_match:
                current_items.append(bullet_match.group(1).strip())
                continue

            # Treat as a standalone skill or label
            current_items.append(stripped)

        if current_items:
            groups.append(SkillsGroup(label=current_label, items=current_items, display_style="inline"))

        if not groups:
            # Fallback: whole text as one group
            groups.append(SkillsGroup(label=None, items=[text.strip()], display_style="inline"))

        return SkillsContent(groups=groups)

    def _parse_items(self, text: str) -> ItemsContent:
        """Parse text as a simple list of items."""
        items = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            bullet_match = _BULLET_RE.match(stripped)
            if bullet_match:
                items.append(bullet_match.group(1).strip())
            else:
                items.append(stripped)
        return ItemsContent(items=items)

    def _parse_bullets_or_prose(self, text: str) -> BulletsContent | ProseContent:
        """Decide if text is bullets or prose based on content."""
        bullets = self._extract_bullets(text)
        if bullets:
            return BulletsContent(bullets=bullets)
        return self._parse_prose(text)

    def _extract_bullets(self, text: str) -> List[str]:
        """Extract bullet points with continuation-line joining."""
        bullets: List[str] = []
        current_bullet: List[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if current_bullet:
                    bullets.append(" ".join(current_bullet))
                    current_bullet = []
                continue

            bullet_match = _BULLET_RE.match(stripped)
            if bullet_match:
                # New bullet — save previous
                if current_bullet:
                    original = "\n".join(current_bullet)
                    joined = " ".join(current_bullet)
                    if original != joined and len(current_bullet) > 1:
                        self._events.append(NormalizationEvent(
                            rule_id="bullet_continuation_join",
                            description=f"Joined {len(current_bullet)} continuation lines into single bullet",
                            before=original,
                            after=joined,
                        ))
                    bullets.append(joined)
                current_bullet = [bullet_match.group(1).strip()]
            elif current_bullet:
                # Continuation of current bullet
                current_bullet.append(stripped)
            # else: non-bullet line before any bullet — skip

        if current_bullet:
            original = "\n".join(current_bullet)
            joined = " ".join(current_bullet)
            if original != joined and len(current_bullet) > 1:
                self._events.append(NormalizationEvent(
                    rule_id="bullet_continuation_join",
                    description=f"Joined {len(current_bullet)} continuation lines into single bullet",
                    before=original,
                    after=joined,
                ))
            bullets.append(joined)

        return bullets

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _strip_section_heading(self, text: str, cat: SectionCategory) -> str:
        """Remove leading line if it's just the section heading baked into content."""
        # Known heading variants per category
        heading_variants = {
            SectionCategory.summary: {"summary", "professional summary", "career summary", "profile", "objective"},
            SectionCategory.skills: {"skills", "key skills", "technical skills", "technical proficiencies"},
            SectionCategory.experience: {"experience", "work experience", "employment history", "work"},
            SectionCategory.education: {"education", "academic background"},
            SectionCategory.certifications: {"certifications", "certificates", "licenses and certifications"},
            SectionCategory.awards: {"awards", "recognitions", "honors"},
            SectionCategory.projects: {"projects"},
        }

        variants = heading_variants.get(cat, set())
        if not variants:
            return text

        lines = text.splitlines()
        if not lines:
            return text

        first_line = lines[0].strip()
        # Check if first line is purely a heading (possibly uppercase)
        if first_line.lower().rstrip(":") in variants:
            stripped = "\n".join(lines[1:]).strip()
            if stripped:
                self._events.append(NormalizationEvent(
                    rule_id="strip_section_heading",
                    description=f"Removed redundant section heading from block text",
                    before=first_line,
                    after="(removed)",
                ))
                return stripped

        return text

    def _clean_artifacts(self, text: str) -> str:
        """Clean common PDF extraction artifacts."""
        result = text
        for pattern, replacement, rule_id in _ARTIFACT_PATTERNS:
            new_result = pattern.sub(replacement, result)
            if new_result != result:
                self._events.append(NormalizationEvent(
                    rule_id=rule_id,
                    description=f"Cleaned extraction artifact: {rule_id}",
                    before=result[:200],
                    after=new_result[:200],
                    severity="info",
                ))
                result = new_result
        return result

    def _parse_date(self, date_str: str | None) -> PartialDate | None:
        """Parse a date string into a PartialDate."""
        if not date_str:
            return None

        raw = date_str.strip()
        if raw.lower() in ("present", "current", "now"):
            return None  # handled by is_current flag

        # Try "Month Year" (e.g., "September 2021", "Sep 2021")
        parts = raw.split()
        if len(parts) == 2:
            month_str, year_str = parts
            month = _MONTH_MAP.get(month_str.lower()) or _MONTH_ABBR_MAP.get(month_str.lower())
            if month and year_str.isdigit():
                return PartialDate(year=int(year_str), month=month, raw_text=raw)

        # Try year only
        if raw.isdigit() and len(raw) == 4:
            return PartialDate(year=int(raw), raw_text=raw)

        # Try "YYYY-MM" or "YYYY-MM-DD"
        iso_match = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", raw)
        if iso_match:
            return PartialDate(
                year=int(iso_match.group(1)),
                month=int(iso_match.group(2)) if iso_match.group(2) else None,
                day=int(iso_match.group(3)) if iso_match.group(3) else None,
                raw_text=raw,
            )

        # Fallback: keep raw text
        return PartialDate(raw_text=raw)

    def _is_current(self, end_date: str | None) -> bool:
        """Check if end_date indicates a current position."""
        if not end_date:
            return False
        return end_date.strip().lower() in ("present", "current", "now")

    def _strip_header_line(self, text: str, block: models.ResumeBlock) -> str:
        """Remove the first line if it duplicates structured metadata."""
        if not (block.job_title or block.company):
            return text
        lines = text.splitlines()
        if not lines:
            return text

        first_norm = lines[0].replace(" ", "").lower()
        meta_parts = [block.job_title, block.company, block.start_date, block.end_date]
        meta_parts = [p for p in meta_parts if p]

        if meta_parts and all(p.replace(" ", "").lower() in first_norm for p in meta_parts):
            stripped = "\n".join(lines[1:]).strip()
            if stripped:
                self._events.append(NormalizationEvent(
                    rule_id="strip_header_line",
                    description="Removed duplicate header line from block text",
                    before=lines[0],
                    after="(removed)",
                ))
                return stripped

        return text

    def _parse_basics(self, text: str, existing: Basics) -> Basics:
        """Extract contact info from a contact block."""
        data = existing.model_dump()

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # Email
            email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", stripped)
            if email_match and not data.get("email"):
                data["email"] = email_match.group(0)

            # Phone
            phone_match = re.search(r"[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}", stripped)
            if phone_match and not data.get("phone"):
                data["phone"] = phone_match.group(0)

            # LinkedIn
            if "linkedin.com" in stripped.lower() and not data.get("linkedin"):
                url_match = re.search(r"https?://\S+linkedin\S+", stripped, re.IGNORECASE)
                data["linkedin"] = url_match.group(0) if url_match else stripped

            # Name: first non-empty line that isn't email/phone/url
            if (
                not data.get("name")
                and not email_match
                and not phone_match
                and "linkedin.com" not in stripped.lower()
                and "http" not in stripped.lower()
                and len(stripped) < 60
            ):
                data["name"] = stripped

            # Location: contains comma (City, State)
            if not data.get("location") and "," in stripped and not email_match:
                if not stripped.startswith("http") and len(stripped) < 80:
                    data["location"] = stripped

        return Basics(**data)
