from pathlib import Path

from backend.db.session import get_session, init_db
from backend.models import models
from backend.services.prefill import PrefillPlanner


def test_prefill_plan_produces_apply_url(tmp_path):
    init_db()
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("Sample resume", encoding="utf-8")

    with get_session() as session:
        company = models.Company(name="TestCo")
        session.add(company)
        session.flush()

        job_posting = models.JobPosting(
            company_id=company.id,
            url="https://example.com/job",
            apply_url="https://example.com/apply",
            title="Engineer",
            location="Remote",
        )
        session.add(job_posting)
        session.flush()

        application = models.Application(job_posting_id=job_posting.id)
        application.resume_artifact_path = str(resume_path)
        session.add(application)
        session.flush()

        job_posting.application = application
        planner = PrefillPlanner(session)
        plan = planner.build_plan(job_posting.id)

    assert plan["apply_url"] == "https://example.com/apply"
    assert plan["uploads"][0]["path"] == str(resume_path)
    assert Path(plan["artifact_dir"]).exists()
