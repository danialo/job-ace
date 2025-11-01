from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.db.session import get_db, init_db
from backend.models import models
from backend.models.schemas import (
    ArtifactPathResponse,
    IntakeRequest,
    IntakeResponse,
    LogSubmitRequest,
    LogSubmitResponse,
    PrefillPlanRequest,
    PrefillPlanResponse,
    TailorRequest,
    TailorResponse,
)
from backend.services.artifacts import ArtifactManager
from backend.services.intake import IntakeService
from backend.services.prefill import PrefillPlanner
from backend.services.submission import SubmissionLogger
from backend.services.tailor import TailorService

app = FastAPI(title="Job Ace API", version="0.1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.post("/intake", response_model=IntakeResponse, status_code=status.HTTP_201_CREATED)
def intake(payload: IntakeRequest, db: Session = Depends(get_db)) -> IntakeResponse:
    service = IntakeService(db)
    job_posting = service.run(payload.url, payload.force)
    artifact_dir = ArtifactManager(db).ensure_job_dir(job_posting)
    return IntakeResponse(job_id=job_posting.id, artifact_dir=artifact_dir)


@app.post("/tailor", response_model=TailorResponse)
def tailor(payload: TailorRequest, db: Session = Depends(get_db)) -> TailorResponse:
    service = TailorService(db)
    try:
        result = service.run(payload.job_id, payload.allowed_block_ids, payload.resume_version)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TailorResponse(**result)


@app.post("/prefill-plan", response_model=PrefillPlanResponse)
def prefill_plan(payload: PrefillPlanRequest, db: Session = Depends(get_db)) -> PrefillPlanResponse:
    planner = PrefillPlanner(db)
    try:
        plan = planner.build_plan(payload.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PrefillPlanResponse(**plan)


@app.post("/log-submit", response_model=LogSubmitResponse)
def log_submit(payload: LogSubmitRequest, db: Session = Depends(get_db)) -> LogSubmitResponse:
    logger = SubmissionLogger(db)
    try:
        application = logger.log(
            payload.job_id,
            payload.confirmation_id,
            payload.confirmation_text,
            payload.screenshot_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return LogSubmitResponse(
        application_id=application.id,
        status=application.status,
        applied_at=application.applied_at,
    )


@app.get("/artifact/{job_id}", response_model=ArtifactPathResponse)
def artifact(job_id: int, kind: str = Query(..., description="Artifact kind label"), db: Session = Depends(get_db)) -> ArtifactPathResponse:
    job_posting = db.get(models.JobPosting, job_id)
    if not job_posting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    artifact_mgr = ArtifactManager(db)
    artifact = artifact_mgr.get_artifact(job_posting, kind)
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact missing")
    return ArtifactPathResponse(path=artifact.path)


@app.get("/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict]:
    """List all job postings."""
    jobs = db.query(models.JobPosting).order_by(models.JobPosting.id.desc()).all()
    return [
        {
            "id": job.id,
            "title": job.title,
            "company": job.company.name if job.company else "Unknown",
            "location": job.location,
            "url": job.url,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }
        for job in jobs
    ]


@app.get("/blocks")
def list_blocks(db: Session = Depends(get_db)) -> list[dict]:
    """List all resume blocks."""
    blocks = db.query(models.ResumeBlock).order_by(models.ResumeBlock.id).all()
    return [
        {
            "id": block.id,
            "category": block.category,
            "tags": block.tags.split(",") if block.tags else [],
            "text": block.text[:100] + "..." if len(block.text) > 100 else block.text,
        }
        for block in blocks
    ]


@app.get("/applications")
def list_applications(db: Session = Depends(get_db)) -> list[dict]:
    """List all applications."""
    apps = db.query(models.Application).order_by(models.Application.applied_at.desc()).all()
    return [
        {
            "id": app.id,
            "job_id": app.job_posting_id,
            "job_title": app.job_posting.title if app.job_posting else "Unknown",
            "status": app.status,
            "applied_at": app.applied_at.isoformat() if app.applied_at else None,
        }
        for app in apps
    ]


# Mount static files AFTER all API routes to avoid conflicts
frontend_dir = Path(__file__).parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir / "static")), name="static")
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
