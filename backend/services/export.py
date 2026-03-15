from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import models

TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "resume"

# Canonical section ordering for resumes
SECTION_ORDER = [
    "contact",
    "summary",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "awards",
    "other",
]

SECTION_HEADINGS = {
    "contact": "Contact",
    "summary": "Professional Summary",
    "experience": "Experience",
    "education": "Education",
    "skills": "Skills",
    "projects": "Projects",
    "certifications": "Certifications",
    "awards": "Awards",
    "other": "Additional",
}


def _text_to_html(text: str) -> str:
    """Convert block text to simple HTML (bullets become <ul>, paragraphs become <p>)."""
    lines = text.strip().splitlines()
    html_parts: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        bullet_match = re.match(r"^[-•●*►▪▸]\s*(.+)$", stripped)
        if bullet_match:
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{bullet_match.group(1)}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p>{stripped}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def _format_dates(start: Optional[str], end: Optional[str]) -> str:
    parts = []
    if start:
        parts.append(start)
    if end:
        parts.append(end)
    return " – ".join(parts) if parts else ""


class ExportService:
    def __init__(self, db: Session):
        self.db = db

    def list_templates(self) -> List[Dict]:
        """Scan template directory for available templates."""
        templates = []
        if not TEMPLATE_DIR.is_dir():
            return templates
        for meta_path in TEMPLATE_DIR.glob("*/meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["id"] = meta_path.parent.name
                templates.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
        return templates

    def render_pdf(
        self,
        job_id: int,
        block_ids: List[int],
        template: str = "classic",
        version: str = "v1",
    ) -> bytes:
        """Render resume blocks as a PDF via HTML+WeasyPrint."""
        import weasyprint

        render_data = self._prepare_render_data(job_id, block_ids)
        template_dir = TEMPLATE_DIR / template
        if not template_dir.is_dir():
            raise ValueError(f"Template '{template}' not found")

        env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
        tmpl = env.get_template("template.html")
        html_string = tmpl.render(**render_data)

        css_path = template_dir / "style.css"
        stylesheets = [weasyprint.CSS(filename=str(css_path))] if css_path.exists() else []

        doc = weasyprint.HTML(string=html_string, base_url=str(template_dir))
        return doc.write_pdf(stylesheets=stylesheets)

    def render_docx(
        self,
        job_id: int,
        block_ids: List[int],
        template: str = "classic",
        version: str = "v1",
    ) -> bytes:
        """Build a DOCX resume programmatically with python-docx."""
        render_data = self._prepare_render_data(job_id, block_ids)
        doc = Document()

        # Set default font
        style = doc.styles["Normal"]
        font = style.font
        font.name = "Calibri"
        font.size = Pt(10.5)

        # Contact header
        contact = render_data.get("contact")
        if contact:
            if contact.get("name"):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(contact["name"])
                run.bold = True
                run.font.size = Pt(16)

            info_parts = []
            for key in ("email", "phone", "location", "linkedin"):
                if contact.get(key):
                    info_parts.append(contact[key])
            if info_parts:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(" | ".join(info_parts))
                run.font.size = Pt(9.5)

        # Sections
        for section in render_data.get("sections", []):
            heading = doc.add_heading(section["heading"], level=2)
            heading.style.font.size = Pt(11)

            for block in section["blocks"]:
                # Experience-style header
                if block.get("job_title") or block.get("company"):
                    p = doc.add_paragraph()
                    if block.get("job_title"):
                        run = p.add_run(block["job_title"])
                        run.bold = True
                    if block.get("company"):
                        run = p.add_run(f" — {block['company']}")
                        run.italic = True
                    if block.get("dates"):
                        run = p.add_run(f"    {block['dates']}")
                        run.font.size = Pt(9.5)

                # Block text: parse bullets vs paragraphs
                text = block.get("text", "")
                for line in text.strip().splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    bullet_match = re.match(r"^[-•●*►▪▸]\s*(.+)$", stripped)
                    if bullet_match:
                        doc.add_paragraph(bullet_match.group(1), style="List Bullet")
                    else:
                        doc.add_paragraph(stripped)

        import io

        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    def _prepare_render_data(self, job_id: int, block_ids: List[int]) -> Dict:
        """Load blocks from DB and group by category in resume-logical order."""
        if not block_ids:
            raise ValueError("No block IDs provided")

        stmt = select(models.ResumeBlock).where(models.ResumeBlock.id.in_(block_ids))
        blocks = self.db.scalars(stmt).all()
        if not blocks:
            raise ValueError("No blocks found for the given IDs")

        # Group blocks by category
        by_category: Dict[str, list] = {}
        contact_info: Dict[str, str] = {}

        for block in blocks:
            cat = (block.category or "other").lower()

            if cat == "contact":
                # Parse contact block text for structured info
                contact_info = self._parse_contact(block.text, contact_info)
                continue

            entry = {
                "text": block.text,
                "html_content": Markup(_text_to_html(block.text)),
                "job_title": block.job_title,
                "company": block.company,
                "dates": _format_dates(block.start_date, block.end_date),
            }
            by_category.setdefault(cat, []).append(entry)

        # Build ordered sections
        sections = []
        for cat in SECTION_ORDER:
            if cat == "contact":
                continue
            if cat in by_category:
                sections.append(
                    {
                        "heading": SECTION_HEADINGS.get(cat, cat.title()),
                        "blocks": by_category[cat],
                    }
                )

        # Any categories not in our canonical order
        for cat, cat_blocks in by_category.items():
            if cat not in SECTION_ORDER:
                sections.append(
                    {
                        "heading": cat.title(),
                        "blocks": cat_blocks,
                    }
                )

        return {
            "contact": contact_info if contact_info else None,
            "sections": sections,
        }

    def _parse_contact(self, text: str, existing: Dict[str, str]) -> Dict[str, str]:
        """Best-effort extraction of contact fields from free-text contact block."""
        info = dict(existing)
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Email
            email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", stripped)
            if email_match and "email" not in info:
                info["email"] = email_match.group(0)
            # Phone
            phone_match = re.search(r"[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}", stripped)
            if phone_match and "phone" not in info:
                info["phone"] = phone_match.group(0)
            # LinkedIn
            if "linkedin.com" in stripped.lower() and "linkedin" not in info:
                url_match = re.search(r"https?://\S+linkedin\S+", stripped, re.IGNORECASE)
                info["linkedin"] = url_match.group(0) if url_match else stripped
            # Name: first non-empty line that isn't email/phone/url
            if (
                "name" not in info
                and not email_match
                and not phone_match
                and "linkedin.com" not in stripped.lower()
                and "http" not in stripped.lower()
                and len(stripped) < 60
            ):
                info["name"] = stripped
            # Location heuristic: contains comma (City, State)
            if "location" not in info and "," in stripped and not email_match:
                if not stripped.startswith("http") and len(stripped) < 80:
                    info["location"] = stripped
        return info
