from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


class Company(Base):
    __tablename__ = "company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    site: Mapped[Optional[str]] = mapped_column(String)
    values_json: Mapped[Optional[str]] = mapped_column(Text)
    tech_stack: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    job_postings: Mapped[list["JobPosting"]] = relationship("JobPosting", back_populates="company")


class JobPosting(Base):
    __tablename__ = "job_posting"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    apply_url: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(String)
    location: Mapped[Optional[str]] = mapped_column(String)
    employment_type: Mapped[Optional[str]] = mapped_column(String)
    seniority: Mapped[Optional[str]] = mapped_column(String)
    salary_min: Mapped[Optional[int]] = mapped_column(Integer)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer)
    deadline: Mapped[Optional[str]] = mapped_column(String)
    portal_hint: Mapped[Optional[str]] = mapped_column(String)
    must_haves_json: Mapped[Optional[str]] = mapped_column(Text)
    nice_to_haves_json: Mapped[Optional[str]] = mapped_column(Text)
    screening_questions_json: Mapped[Optional[str]] = mapped_column(Text)
    jd_json_path: Mapped[Optional[str]] = mapped_column(Text)
    analysis_json_path: Mapped[Optional[str]] = mapped_column(Text)
    captured_html_path: Mapped[Optional[str]] = mapped_column(Text)
    captured_pdf_path: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="intake", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    company: Mapped[Company] = relationship("Company", back_populates="job_postings")
    application: Mapped[Optional["Application"]] = relationship(
        "Application", back_populates="job_posting", uselist=False
    )
    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="job_posting")


class Application(Base):
    __tablename__ = "application"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.id"), nullable=False)
    portal: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="draft", nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    confirmation_id: Mapped[Optional[str]] = mapped_column(String)
    confirmation_text: Mapped[Optional[str]] = mapped_column(Text)
    resume_artifact_path: Mapped[Optional[str]] = mapped_column(Text)
    cover_artifact_path: Mapped[Optional[str]] = mapped_column(Text)
    compliance_report_path: Mapped[Optional[str]] = mapped_column(Text)
    followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    job_posting: Mapped[JobPosting] = relationship("JobPosting", back_populates="application")
    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="application")
    block_usage: Mapped[list["ResumeBlockUsage"]] = relationship(
        "ResumeBlockUsage", back_populates="application"
    )


class Artifact(Base):
    __tablename__ = "artifact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.id"), nullable=False)
    application_id: Mapped[Optional[int]] = mapped_column(ForeignKey("application.id"))
    kind: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    job_posting: Mapped[JobPosting] = relationship("JobPosting", back_populates="artifacts")
    application: Mapped[Optional[Application]] = relationship("Application", back_populates="artifacts")

    __table_args__ = (UniqueConstraint("kind", "path", name="uq_artifact_kind_path"),)


class ResumeBlock(Base):
    __tablename__ = "resume_block"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String)
    tags: Mapped[Optional[str]] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    job_title: Mapped[Optional[str]] = mapped_column(String)
    company: Mapped[Optional[str]] = mapped_column(String)
    start_date: Mapped[Optional[str]] = mapped_column(String)
    end_date: Mapped[Optional[str]] = mapped_column(String)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    usages: Mapped[list["ResumeBlockUsage"]] = relationship(
        "ResumeBlockUsage", back_populates="resume_block"
    )


class ResumeBlockUsage(Base):
    __tablename__ = "resume_block_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"), nullable=False)
    resume_block_id: Mapped[int] = mapped_column(ForeignKey("resume_block.id"), nullable=False)
    used_in: Mapped[str] = mapped_column(String, nullable=False)

    application: Mapped[Application] = relationship("Application", back_populates="block_usage")
    resume_block: Mapped[ResumeBlock] = relationship("ResumeBlock", back_populates="usages")

    __table_args__ = (
        UniqueConstraint("application_id", "resume_block_id", "used_in", name="uq_block_usage"),
    )
