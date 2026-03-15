"""Tests for the ResumeNormalizer and ResumeDocument model."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from backend.db.session import Base, engine, get_session
from backend.models.models import ResumeBlock
from backend.models.resume_document import (
    BulletsContent,
    ItemsContent,
    PartialDate,
    ProseContent,
    ResumeDocument,
    SectionCategory,
    SkillsContent,
)
from backend.services.resume_normalizer import ResumeNormalizer


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    with get_session() as session:
        yield session


def _add_block(db, **kwargs) -> int:
    block = ResumeBlock(**kwargs)
    db.add(block)
    db.flush()
    return block.id


# ---------------------------------------------------------------------------
# Bullet continuation joining
# ---------------------------------------------------------------------------

class TestBulletContinuation:
    def test_multiline_bullet_joined(self, db):
        block_id = _add_block(
            db,
            category="experience",
            text=(
                "● Serve as primary support contact for strategic FlashArray customers, specializing in root-cause\n"
                "analysis, timeline forensics, and triage of complex break/fix issues including controller interrupts,\n"
                "Fibre Channel anomalies, and ActiveCluster replication faults.\n"
                "● Provide continuity coverage for multiple accounts."
            ),
            job_title="DSE",
            company="Pure Storage",
            start_date="2022",
            end_date="Present",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        section = doc.sections[0]
        entry = section.entries[0]
        assert isinstance(entry.content, BulletsContent)
        assert len(entry.content.bullets) == 2

        first_bullet = entry.content.bullets[0]
        assert "root-cause analysis" in first_bullet
        assert "ActiveCluster replication faults" in first_bullet
        assert "\n" not in first_bullet

    def test_single_line_bullets_unchanged(self, db):
        block_id = _add_block(
            db,
            category="experience",
            text="● Built REST APIs\n● Deployed to production\n● Wrote tests",
            job_title="Dev",
            company="Acme",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        content = doc.sections[0].entries[0].content
        assert isinstance(content, BulletsContent)
        assert len(content.bullets) == 3
        assert content.bullets[0] == "Built REST APIs"


# ---------------------------------------------------------------------------
# Skills parsing
# ---------------------------------------------------------------------------

class TestSkillsParsing:
    def test_pipe_delimited_skills(self, db):
        block_id = _add_block(
            db,
            category="skills",
            text="| Python | Bash | JSON | YAML | Windows | Linux |",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        content = doc.sections[0].entries[0].content
        assert isinstance(content, SkillsContent)
        assert len(content.groups) >= 1
        items = content.groups[0].items
        assert "Python" in items
        assert "Linux" in items

    def test_labeled_skill_groups(self, db):
        block_id = _add_block(
            db,
            category="skills",
            text="KEY SKILLS\n| Prompt Engineering | AI Workflow Design | Systems Thinking |\nTECHNICAL PROFICIENCIES\n| Python | Bash | JSON | YAML |",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        content = doc.sections[0].entries[0].content
        assert isinstance(content, SkillsContent)
        assert len(content.groups) >= 2

    def test_comma_separated_skills(self, db):
        block_id = _add_block(
            db,
            category="skills",
            text="Python, Go, PostgreSQL, Docker, Kubernetes, AWS",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        content = doc.sections[0].entries[0].content
        assert isinstance(content, SkillsContent)
        items = content.groups[0].items
        assert "Python" in items
        assert "AWS" in items


# ---------------------------------------------------------------------------
# Summary as prose
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_becomes_prose(self, db):
        block_id = _add_block(
            db,
            category="summary",
            text="Experienced engineer with 8 years of experience building distributed systems.",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        content = doc.sections[0].entries[0].content
        assert isinstance(content, ProseContent)
        assert len(content.paragraphs) == 1
        assert "distributed systems" in content.paragraphs[0]


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

class TestDateParsing:
    def test_month_year(self, db):
        block_id = _add_block(
            db,
            category="experience",
            text="● Did things",
            job_title="Dev",
            company="Acme",
            start_date="September 2021",
            end_date="Present",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        header = doc.sections[0].entries[0].header
        assert header.start_date.year == 2021
        assert header.start_date.month == 9
        assert header.is_current is True
        assert header.end_date is None

    def test_year_only(self, db):
        block_id = _add_block(
            db,
            category="education",
            text="BS Computer Science",
            company="MIT",
            start_date="2012",
            end_date="2016",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        header = doc.sections[0].entries[0].header
        assert header.start_date.year == 2012
        assert header.end_date.year == 2016
        assert header.is_current is False

    def test_abbreviated_month(self, db):
        block_id = _add_block(
            db,
            category="experience",
            text="● Worked",
            job_title="Dev",
            company="X",
            start_date="Jan 2020",
            end_date="Dec 2022",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        header = doc.sections[0].entries[0].header
        assert header.start_date.month == 1
        assert header.end_date.month == 12


# ---------------------------------------------------------------------------
# Contact / Basics
# ---------------------------------------------------------------------------

class TestBasics:
    def test_contact_block_parsed(self, db):
        block_id = _add_block(
            db,
            category="contact",
            text="Jane Doe\njane@example.com\n555-123-4567\nSan Francisco, CA",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        assert doc.basics.name == "Jane Doe"
        assert doc.basics.email == "jane@example.com"
        assert doc.basics.phone == "555-123-4567"
        assert "San Francisco" in doc.basics.location


# ---------------------------------------------------------------------------
# Certifications / Items
# ---------------------------------------------------------------------------

class TestItems:
    def test_certs_become_items(self, db):
        block_id = _add_block(
            db,
            category="certifications",
            text="FlashArray Implementation Specialist\nCompTIA Network+\nCompTIA A+",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        content = doc.sections[0].entries[0].content
        assert isinstance(content, ItemsContent)
        assert len(content.items) == 3
        assert "CompTIA A+" in content.items


# ---------------------------------------------------------------------------
# Artifact cleanup
# ---------------------------------------------------------------------------

class TestArtifactCleanup:
    def test_split_word_fixed(self, db):
        block_id = _add_block(
            db,
            category="experience",
            text="● Worked from 2022 to Pr esent",
            job_title="Dev",
            company="X",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        bullet_text = doc.sections[0].entries[0].content.bullets[0]
        assert "Present" in bullet_text
        assert "Pr esent" not in bullet_text

    def test_space_before_hyphen_fixed(self, db):
        block_id = _add_block(
            db,
            category="experience",
            text="● Built customer -ready slide decks",
            job_title="Dev",
            company="X",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        bullet_text = doc.sections[0].entries[0].content.bullets[0]
        assert "customer-ready" in bullet_text


# ---------------------------------------------------------------------------
# Section ordering
# ---------------------------------------------------------------------------

class TestSectionOrdering:
    def test_sections_ordered_correctly(self, db):
        ids = [
            _add_block(db, category="certifications", text="CompTIA A+"),
            _add_block(db, category="summary", text="Experienced engineer."),
            _add_block(
                db, category="experience", text="● Built things",
                job_title="Dev", company="X",
            ),
            _add_block(db, category="skills", text="Python, Go"),
        ]
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize(ids)

        categories = [s.category for s in doc.sections]
        assert categories.index(SectionCategory.summary) < categories.index(SectionCategory.experience)
        assert categories.index(SectionCategory.skills) < categories.index(SectionCategory.certifications)


# ---------------------------------------------------------------------------
# Normalization events tracked
# ---------------------------------------------------------------------------

class TestNormalizationEvents:
    def test_continuation_join_recorded(self, db):
        block_id = _add_block(
            db,
            category="experience",
            text="● Long bullet that wraps\nacross multiple lines\n● Short bullet",
            job_title="Dev",
            company="X",
        )
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize([block_id])

        join_events = [e for e in doc.metadata.normalization_events if e.rule_id == "bullet_continuation_join"]
        assert len(join_events) >= 1


# ---------------------------------------------------------------------------
# Full document round-trip
# ---------------------------------------------------------------------------

class TestDocumentSerialization:
    def test_serialize_deserialize(self, db):
        ids = [
            _add_block(db, category="contact", text="Jane Doe\njane@example.com"),
            _add_block(db, category="summary", text="Senior engineer."),
            _add_block(
                db, category="experience", text="● Built APIs\n● Led team",
                job_title="SWE", company="Acme", start_date="2020", end_date="Present",
            ),
            _add_block(db, category="skills", text="| Python | Go | Rust |"),
        ]
        db.commit()

        normalizer = ResumeNormalizer(db)
        doc = normalizer.normalize(ids)

        # Serialize to JSON and back
        json_str = doc.model_dump_json(indent=2)
        restored = ResumeDocument.model_validate_json(json_str)

        assert restored.basics.name == "Jane Doe"
        assert len(restored.sections) == len(doc.sections)
        assert restored.sections[0].category == doc.sections[0].category
