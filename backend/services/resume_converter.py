from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

NS = "http://job-ace.local/resume"


class ResumeConverter:
    """Convert resumes from various formats to XML blocks."""

    def __init__(self):
        self.logger = logger.bind(service="resume_converter")

    def parse_text_resume(self, text: str) -> dict[str, Any]:
        """Parse a text resume and extract structured data."""
        self.logger.info("parsing_text_resume", length=len(text))

        # Initialize structure
        resume_data = {
            "metadata": {},
            "blocks": []
        }

        # Extract metadata from top of resume
        lines = text.strip().split('\n')
        metadata_lines = []
        content_start = 0

        # First few lines often contain contact info
        for i, line in enumerate(lines[:10]):
            line = line.strip()
            if not line:
                continue

            # Email
            email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', line)
            if email_match:
                resume_data["metadata"]["email"] = email_match.group()
                metadata_lines.append(i)

            # Phone
            phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', line)
            if phone_match:
                resume_data["metadata"]["phone"] = phone_match.group()
                metadata_lines.append(i)

            # LinkedIn
            if 'linkedin.com' in line.lower():
                resume_data["metadata"]["linkedin"] = line
                metadata_lines.append(i)

            # GitHub
            if 'github.com' in line.lower():
                resume_data["metadata"]["github"] = line
                metadata_lines.append(i)

            # Name (usually first non-empty line)
            if i == 0 or (i == 1 and not lines[0].strip()):
                resume_data["metadata"]["name"] = line

        # Find sections
        sections = self._identify_sections(text)

        # Convert sections to blocks
        block_id = 1
        for section_name, section_content in sections.items():
            category = self._categorize_section(section_name)
            tags = self._extract_tags(section_content, category)

            block = {
                "id": f"{category}-{block_id}",
                "category": category,
                "tags": tags,
                "content": section_content.strip(),
                "metadata": self._extract_block_metadata(section_content, category)
            }
            resume_data["blocks"].append(block)
            block_id += 1

        return resume_data

    def _identify_sections(self, text: str) -> dict[str, str]:
        """Identify resume sections based on common headers."""
        sections = {}
        current_section = "summary"
        current_content = []

        lines = text.split('\n')

        # Common section headers
        section_patterns = {
            r'(summary|professional summary|profile|objective)': 'summary',
            r'(experience|work experience|employment|professional experience)': 'experience',
            r'(education|academic|qualifications)': 'education',
            r'(skills|technical skills|core competencies)': 'skills',
            r'(projects|personal projects)': 'projects',
            r'(certifications|certificates)': 'certifications',
            r'(awards|achievements|honors)': 'awards',
        }

        for line in lines:
            line_lower = line.strip().lower()

            # Check if this line is a section header
            is_header = False
            for pattern, section_name in section_patterns.items():
                if re.match(f'^{pattern}:?$', line_lower):
                    # Save previous section
                    if current_content:
                        sections[current_section] = '\n'.join(current_content)
                        current_content = []

                    current_section = section_name
                    is_header = True
                    break

            if not is_header and line.strip():
                current_content.append(line)

        # Save final section
        if current_content:
            sections[current_section] = '\n'.join(current_content)

        return sections

    def _categorize_section(self, section_name: str) -> str:
        """Categorize a section into standard categories."""
        section_map = {
            'summary': 'summary',
            'experience': 'experience',
            'education': 'education',
            'skills': 'skills',
            'projects': 'projects',
            'certifications': 'certifications',
            'awards': 'awards',
        }
        return section_map.get(section_name, 'other')

    def _extract_tags(self, content: str, category: str) -> list[str]:
        """Extract relevant tags from content."""
        tags = []

        # Technology keywords
        tech_keywords = [
            'python', 'javascript', 'typescript', 'java', 'c++', 'go', 'rust', 'ruby',
            'react', 'vue', 'angular', 'fastapi', 'django', 'flask', 'node',
            'postgresql', 'mysql', 'mongodb', 'redis', 'sql',
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'ci/cd',
            'machine learning', 'ai', 'data science', 'backend', 'frontend', 'full-stack'
        ]

        content_lower = content.lower()
        for keyword in tech_keywords:
            if keyword in content_lower:
                tags.append(keyword.replace(' ', '-'))

        # Add category as tag
        tags.append(category)

        return list(set(tags))  # Remove duplicates

    def _extract_block_metadata(self, content: str, category: str) -> dict[str, str]:
        """Extract metadata from block content."""
        metadata = {}

        if category == 'experience':
            # Try to extract company and title
            lines = content.split('\n')
            if lines:
                first_line = lines[0]

                # Pattern: "Title - Company (dates)"
                match = re.search(r'^(.+?)\s*[-–]\s*(.+?)\s*\((\d{4}.*?)\)', first_line)
                if match:
                    metadata['title'] = match.group(1).strip()
                    metadata['company'] = match.group(2).strip()

                    # Extract dates
                    dates = match.group(3)
                    date_parts = re.findall(r'\d{4}', dates)
                    if len(date_parts) >= 1:
                        metadata['start_date'] = date_parts[0]
                    if len(date_parts) >= 2:
                        metadata['end_date'] = date_parts[1]
                    elif 'present' in dates.lower():
                        metadata['end_date'] = 'Present'

        return metadata

    def to_xml(self, resume_data: dict[str, Any]) -> str:
        """Convert resume data to XML format."""
        # Create root element
        root = ET.Element(f'{{{NS}}}resume')
        root.set('version', '1.0')

        # Add metadata
        if resume_data.get('metadata'):
            metadata_elem = ET.SubElement(root, f'{{{NS}}}metadata')
            for key, value in resume_data['metadata'].items():
                if value:
                    elem = ET.SubElement(metadata_elem, f'{{{NS}}}{key}')
                    elem.text = str(value)

        # Add blocks
        blocks_elem = ET.SubElement(root, f'{{{NS}}}blocks')

        for block in resume_data['blocks']:
            block_elem = ET.SubElement(blocks_elem, f'{{{NS}}}block')
            if 'id' in block:
                block_elem.set('id', block['id'])

            # Category
            category_elem = ET.SubElement(block_elem, f'{{{NS}}}category')
            category_elem.text = block['category']

            # Tags
            if block.get('tags'):
                tags_elem = ET.SubElement(block_elem, f'{{{NS}}}tags')
                for tag in block['tags']:
                    tag_elem = ET.SubElement(tags_elem, f'{{{NS}}}tag')
                    tag_elem.text = tag

            # Content
            content_elem = ET.SubElement(block_elem, f'{{{NS}}}content')
            content_elem.text = block['content']

            # Block metadata
            if block.get('metadata'):
                block_metadata_elem = ET.SubElement(block_elem, f'{{{NS}}}metadata')
                for key, value in block['metadata'].items():
                    if value:
                        elem = ET.SubElement(block_metadata_elem, f'{{{NS}}}{key}')
                        elem.text = str(value)

        # Convert to string
        ET.register_namespace('', NS)
        tree = ET.ElementTree(root)

        # Use a temporary file to get pretty XML
        import io
        output = io.BytesIO()
        tree.write(output, encoding='utf-8', xml_declaration=True)
        xml_str = output.getvalue().decode('utf-8')

        # Pretty print
        return self._prettify_xml(xml_str)

    def _prettify_xml(self, xml_string: str) -> str:
        """Add indentation to XML string."""
        try:
            import xml.dom.minidom
            dom = xml.dom.minidom.parseString(xml_string)
            return dom.toprettyxml(indent="  ")
        except Exception:
            return xml_string

    def convert_file(self, file_path: Path) -> str:
        """Convert a resume file to XML."""
        self.logger.info("converting_file", path=str(file_path), suffix=file_path.suffix)

        if file_path.suffix.lower() == '.txt':
            text = file_path.read_text(encoding='utf-8')
        elif file_path.suffix.lower() == '.pdf':
            text = self._extract_pdf_text(file_path)
        elif file_path.suffix.lower() in ['.docx', '.doc']:
            text = self._extract_docx_text(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

        resume_data = self.parse_text_resume(text)
        return self.to_xml(resume_data)

    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF file."""
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            text = []
            for page in reader.pages:
                text.append(page.extract_text())
            return '\n'.join(text)
        except ImportError:
            raise ImportError("pypdf not installed. Run: pip install pypdf")

    def _extract_docx_text(self, file_path: Path) -> str:
        """Extract text from DOCX file."""
        try:
            import docx
            doc = docx.Document(str(file_path))
            return '\n'.join([para.text for para in doc.paragraphs])
        except ImportError:
            raise ImportError("python-docx not installed. Run: pip install python-docx")
