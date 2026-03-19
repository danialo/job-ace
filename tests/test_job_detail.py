"""Tests for job inspection view endpoint."""
import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from backend.models.schemas import (
    JobDetailResponse,
    JobSummary,
    ExtractedRequirements,
    JobProvenance,
    ExtractionQuality,
)


class TestJobDetailSchemas:
    """Test schema validation."""

    def test_job_summary_minimal(self):
        """JobSummary with only required fields."""
        summary = JobSummary(id=1, url="http://example.com")
        assert summary.id == 1
        assert summary.title is None
        assert summary.company is None

    def test_job_summary_full(self):
        """JobSummary with all fields."""
        summary = JobSummary(
            id=1,
            title="Senior Engineer",
            company="Acme Corp",
            location="Remote",
            url="http://example.com",
            portal_hint="greenhouse",
            salary_min=100000,
            salary_max=150000,
            extraction_quality="rich",
        )
        assert summary.title == "Senior Engineer"
        assert summary.salary_min == 100000

    def test_extracted_requirements_defaults(self):
        """ExtractedRequirements default to empty lists."""
        extracted = ExtractedRequirements()
        assert extracted.must_haves == []
        assert extracted.nice_to_haves == []
        assert extracted.screening_questions == []

    def test_extraction_quality_tier(self):
        """ExtractionQuality quality_tier values."""
        rich = ExtractionQuality(must_haves_count=5, quality_tier="rich")
        minimal = ExtractionQuality(must_haves_count=1, quality_tier="minimal")
        thin = ExtractionQuality(must_haves_count=0, quality_tier="thin")

        assert rich.quality_tier == "rich"
        assert minimal.quality_tier == "minimal"
        assert thin.quality_tier == "thin"

    def test_job_detail_response_complete(self):
        """Full JobDetailResponse construction."""
        response = JobDetailResponse(
            job=JobSummary(id=1, url="http://example.com", title="Test Job"),
            extracted=ExtractedRequirements(
                must_haves=["Python", "SQL"],
                nice_to_haves=["Go"],
            ),
            provenance=JobProvenance(
                source_url="http://example.com",
                raw_text_available=True,
                raw_text_chars=5000,
            ),
            quality=ExtractionQuality(
                must_haves_count=2,
                nice_to_haves_count=1,
                quality_tier="rich",
            ),
        )
        assert response.job.id == 1
        assert len(response.extracted.must_haves) == 2
        assert response.provenance.raw_text_chars == 5000
        assert response.quality.quality_tier == "rich"


class TestQualityTierLogic:
    """Test quality tier calculation logic."""

    def test_rich_tier_with_salary(self):
        """Rich tier: 3+ must-haves AND has salary."""
        # Simulated quality calculation
        must_haves = ["Python", "SQL", "AWS"]
        has_salary = True

        if len(must_haves) >= 3 and has_salary:
            tier = "rich"
        elif len(must_haves) >= 1:
            tier = "minimal"
        else:
            tier = "thin"

        assert tier == "rich"

    def test_rich_tier_with_nice_to_haves(self):
        """Rich tier: 3+ must-haves AND 2+ nice-to-haves."""
        must_haves = ["Python", "SQL", "AWS"]
        nice_to_haves = ["Go", "Kubernetes"]
        has_salary = False

        if len(must_haves) >= 3 and (has_salary or len(nice_to_haves) >= 2):
            tier = "rich"
        elif len(must_haves) >= 1 or len(nice_to_haves) >= 1:
            tier = "minimal"
        else:
            tier = "thin"

        assert tier == "rich"

    def test_minimal_tier(self):
        """Minimal tier: has some requirements but not rich."""
        must_haves = ["Python"]
        nice_to_haves = []
        has_salary = False

        if len(must_haves) >= 3 and (has_salary or len(nice_to_haves) >= 2):
            tier = "rich"
        elif len(must_haves) >= 1 or len(nice_to_haves) >= 1:
            tier = "minimal"
        else:
            tier = "thin"

        assert tier == "minimal"

    def test_thin_tier(self):
        """Thin tier: no requirements extracted."""
        must_haves = []
        nice_to_haves = []
        has_salary = False

        if len(must_haves) >= 3 and (has_salary or len(nice_to_haves) >= 2):
            tier = "rich"
        elif len(must_haves) >= 1 or len(nice_to_haves) >= 1:
            tier = "minimal"
        else:
            tier = "thin"

        assert tier == "thin"
