from __future__ import annotations

from pathlib import Path

import tempfile

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.db.session import get_db, init_db
from backend.models import models
from backend.models.schemas import (
    ArtifactPathResponse,
    ConfirmResumeBlocksRequest,
    ConfirmResumeBlocksResponse,
    DeleteBlockResponse,
    ExportRequest,
    ImproveBlockResponse,
    IntakeRequest,
    IntakeResponse,
    LogSubmitRequest,
    LogSubmitResponse,
    ParseResumeResponse,
    PrefillPlanRequest,
    PrefillPlanResponse,
    TailorRequest,
    TailorResponse,
    TemplateInfo,
    UpdateBlockRequest,
    UpdateBlockResponse,
)
from backend.services.artifacts import ArtifactManager
from backend.services.export import ExportService
from backend.services.intake import IntakeService
from backend.services.prefill import PrefillPlanner
from backend.services.resume_converter import ResumeConverter
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
            "text": block.text,
            "job_title": block.job_title,
            "company": block.company,
            "start_date": block.start_date,
            "end_date": block.end_date,
        }
        for block in blocks
    ]


@app.post("/upload-resume", status_code=status.HTTP_201_CREATED)
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    """Upload and parse a resume file, automatically loading blocks into database."""
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ['.pdf', '.docx', '.doc', '.txt']:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {file_ext}. Please upload PDF, DOCX, or TXT."
        )

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)

    try:
        # Get LLM client for resume parsing (o3-mini)
        from backend.services.llm import get_llm_client
        from backend.config import get_settings
        settings = get_settings()
        llm_client = get_llm_client(settings, task="resume_parsing")

        # Parse resume using ResumeConverter with LLM
        converter = ResumeConverter(llm_client=llm_client)

        # Extract text based on file type
        if file_ext == '.txt':
            text = tmp_path.read_text(encoding='utf-8')
        elif file_ext == '.pdf':
            text = converter._extract_pdf_text(tmp_path)
        else:  # .docx or .doc
            text = converter._extract_docx_text(tmp_path)

        # Parse text into structured blocks using LLM
        resume_data = converter.parse_text_resume(text)
        blocks_data = resume_data.get("blocks", [])

        if not blocks_data:
            raise HTTPException(status_code=400, detail="No resume blocks could be extracted from the file")

        # Load blocks into database
        block_ids = []
        for block_data in blocks_data:
            block = models.ResumeBlock(
                category=block_data.get("category"),
                tags=",".join(block_data.get("tags", [])),
                text=block_data.get("content", ""),  # Note: converter uses "content", DB uses "text"
                job_title=block_data.get("job_title"),
                company=block_data.get("company"),
                start_date=block_data.get("start_date"),
                end_date=block_data.get("end_date"),
            )
            db.add(block)
            db.flush()  # Flush to get the ID
            block_ids.append(block.id)

        db.commit()

        return {
            "message": "Resume uploaded and blocks loaded successfully",
            "filename": file.filename,
            "blocks_loaded": len(block_ids),
            "block_ids": block_ids,
            "metadata": resume_data.get("metadata", {}),
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")

    finally:
        # Clean up temporary file
        if tmp_path.exists():
            tmp_path.unlink()


@app.post("/parse-resume", response_model=ParseResumeResponse)
async def parse_resume(file: UploadFile = File(...), db: Session = Depends(get_db)) -> ParseResumeResponse:
    """Parse a resume file and return blocks for preview (does NOT save to database)."""
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ['.pdf', '.docx', '.doc', '.txt']:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {file_ext}. Please upload PDF, DOCX, or TXT."
        )

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)

    try:
        # Get LLM client for resume parsing
        from backend.services.llm import get_llm_client
        from backend.config import get_settings
        settings = get_settings()
        llm_client = get_llm_client(settings, task="resume_parsing")

        # Parse resume using ResumeConverter with LLM
        converter = ResumeConverter(llm_client=llm_client)

        # Extract text based on file type
        if file_ext == '.txt':
            text = tmp_path.read_text(encoding='utf-8')
        elif file_ext == '.pdf':
            text = converter._extract_pdf_text(tmp_path)
        else:  # .docx or .doc
            text = converter._extract_docx_text(tmp_path)

        # Parse text into structured blocks using LLM (multi-stage)
        resume_data = converter.parse_text_resume(text)
        blocks_data = resume_data.get("blocks", [])

        if not blocks_data:
            raise HTTPException(status_code=400, detail="No resume blocks could be extracted from the file")

        # Convert blocks to response format (preview only, not saved)
        from backend.models.schemas import ParsedBlock, ResumeSectionInfo
        parsed_blocks = [
            ParsedBlock(
                category=block.get("category", "other"),
                tags=block.get("tags", []),
                content=block.get("content", ""),
                job_title=block.get("job_title"),
                company=block.get("company"),
                start_date=block.get("start_date"),
                end_date=block.get("end_date"),
            )
            for block in blocks_data
        ]

        # Convert section info if available
        sections_info = None
        if resume_data.get("sections"):
            sections_info = [
                ResumeSectionInfo(
                    name=section["name"],
                    category=section["category"],
                    start_char=section["start_char"],
                    end_char=section["end_char"],
                    estimated_tokens=section["estimated_tokens"],
                )
                for section in resume_data["sections"]
            ]

        return ParseResumeResponse(
            blocks=parsed_blocks,
            metadata=resume_data.get("metadata", {}),
            sections=sections_info,
            parsing_summary=resume_data.get("parsing_summary"),
            original_text=text,  # Include original text for side-by-side comparison
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")

    finally:
        # Clean up temporary file
        if tmp_path.exists():
            tmp_path.unlink()


@app.post("/confirm-resume-blocks", response_model=ConfirmResumeBlocksResponse, status_code=status.HTTP_201_CREATED)
def confirm_resume_blocks(payload: ConfirmResumeBlocksRequest, db: Session = Depends(get_db)) -> ConfirmResumeBlocksResponse:
    """Confirm and save parsed resume blocks to database."""
    if not payload.blocks:
        raise HTTPException(status_code=400, detail="No blocks provided")

    try:
        block_ids = []
        for block_data in payload.blocks:
            block = models.ResumeBlock(
                category=block_data.category,
                tags=",".join(block_data.tags),
                text=block_data.content,
                job_title=block_data.job_title,
                company=block_data.company,
                start_date=block_data.start_date,
                end_date=block_data.end_date,
            )
            db.add(block)
            db.flush()  # Flush to get the ID
            block_ids.append(block.id)

        db.commit()

        return ConfirmResumeBlocksResponse(
            message="Resume blocks saved successfully",
            blocks_saved=len(block_ids),
            block_ids=block_ids,
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving blocks: {str(e)}")


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


@app.put("/blocks/{block_id}", response_model=UpdateBlockResponse)
def update_block(block_id: int, payload: UpdateBlockRequest, db: Session = Depends(get_db)) -> UpdateBlockResponse:
    """Update a resume block."""
    block = db.get(models.ResumeBlock, block_id)
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    # Update fields if provided
    if payload.category is not None:
        block.category = payload.category
    if payload.tags is not None:
        block.tags = payload.tags
    if payload.text is not None:
        block.text = payload.text
    if payload.job_title is not None:
        block.job_title = payload.job_title
    if payload.company is not None:
        block.company = payload.company
    if payload.start_date is not None:
        block.start_date = payload.start_date
    if payload.end_date is not None:
        block.end_date = payload.end_date

    db.commit()
    db.refresh(block)

    return UpdateBlockResponse(
        id=block.id,
        category=block.category,
        tags=block.tags,
        text=block.text,
        job_title=block.job_title,
        company=block.company,
        start_date=block.start_date,
        end_date=block.end_date,
    )


@app.delete("/blocks/{block_id}", response_model=DeleteBlockResponse)
def delete_block(block_id: int, db: Session = Depends(get_db)) -> DeleteBlockResponse:
    """Delete a resume block."""
    block = db.get(models.ResumeBlock, block_id)
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    db.delete(block)
    db.commit()

    return DeleteBlockResponse(id=block_id)


@app.post("/blocks/{block_id}/polish", response_model=ImproveBlockResponse)
def polish_block(
    block_id: int,
    db: Session = Depends(get_db),
) -> ImproveBlockResponse:
    """Polish a resume block — job-agnostic clarity and quality improvement."""
    block = db.get(models.ResumeBlock, block_id)
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    from backend.services.llm import get_llm_client, OpenAIClient
    from backend.config import get_settings
    settings = get_settings()
    llm_client = get_llm_client(settings, task="tailoring")

    prompt = f"""You are polishing a single WORK EXPERIENCE entry from a resume.

Your job is to improve clarity, readability, grammar, and professional presentation while preserving all factual meaning.

GOAL:
Rewrite this work experience entry so it is:
- cleaner
- tighter
- easier to read
- more consistent
- more professional

NON-NEGOTIABLE RULES:
1. DO NOT invent facts.
2. DO NOT add metrics, percentages, time savings, business impact, scale, or outcomes unless explicitly stated in the source text.
3. DO NOT add tools, technologies, responsibilities, certifications, or achievements not present in the source text.
4. DO NOT change job title, company name, or date range.
5. DO NOT strengthen claims beyond what the source text supports.
6. DO NOT remove important technical specificity.
7. DO NOT rewrite the experience to sound more senior, strategic, or leadership-oriented unless the source explicitly supports that.
8. Preserve the original meaning of every bullet.

ALLOWED CHANGES:
- Fix grammar, punctuation, and awkward phrasing
- Tighten sentence structure
- Improve bullet consistency and parallelism
- Replace weak or repetitive wording with stronger accurate wording
- Break overly long bullets for readability
- Merge redundant bullets only if no meaning is lost
- Improve formatting and readability of the section

STYLE RULES:
- Keep the original structure: header + bullet list
- Keep approximately the same number of bullets unless combining duplicates improves clarity
- Use concise, professional, credible language
- Prefer clear and specific wording over generic corporate language
- Avoid filler like "results-driven," "dynamic," "passionate," or "team player"
- Avoid keyword stuffing
- Avoid exaggerated language

OUTPUT REQUIREMENTS:
Return only the polished work experience entry.
Preserve this format:
- First line: Job Title, Company, Date Range
- Then bullet points
No commentary.
No explanations.
No notes.
No markdown fences.

SOURCE WORK EXPERIENCE ENTRY:
{block.text}"""

    try:
        if isinstance(llm_client, OpenAIClient):
            response = llm_client.client.chat.completions.create(
                model=llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            improved_text = response.choices[0].message.content
        else:
            improved_text = block.text

        return ImproveBlockResponse(
            improved_text=improved_text.strip(),
            original_text=block.text,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to polish block: {str(e)}")


@app.post("/blocks/{block_id}/align", response_model=ImproveBlockResponse)
def align_block(
    block_id: int,
    job_id: int = Query(..., description="Job ID to align the block to"),
    db: Session = Depends(get_db),
) -> ImproveBlockResponse:
    """Align a resume block to a specific job posting — targeted rewrite."""
    block = db.get(models.ResumeBlock, block_id)
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    from backend.services.llm import get_llm_client, OpenAIClient
    from backend.config import get_settings
    settings = get_settings()
    llm_client = get_llm_client(settings, task="tailoring")

    # Load job posting
    job_posting = db.get(models.JobPosting, job_id)
    if not job_posting or not job_posting.jd_json_path:
        raise HTTPException(status_code=400, detail="Job posting or JD not found")
    try:
        job_posting_text = Path(job_posting.jd_json_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Job description file not found")

    prompt = f"""You are rewriting a single WORK EXPERIENCE entry from a resume.

Your job is to improve the writing quality while preserving factual accuracy.

GOAL:
Rewrite this work experience entry so it is:
- clearer
- tighter
- more professional
- stronger in phrasing
- better aligned to the target job posting

NON-NEGOTIABLE RULES:
1. DO NOT invent facts.
2. DO NOT add metrics, percentages, time savings, scale, business impact, or outcomes unless they are explicitly stated in the source text.
3. DO NOT claim ownership or leadership beyond what the source text supports.
4. DO NOT add tools, technologies, certifications, responsibilities, or achievements that are not explicitly present.
5. DO NOT change dates, titles, company names, or employment scope.
6. DO NOT remove important technical specificity unless replacing it with equally accurate wording.
7. DO NOT turn implied value into stated measurable impact.
8. If a stronger version would require missing evidence, keep the wording conservative.

ALLOWED IMPROVEMENTS:
- Improve grammar and readability
- Tighten phrasing
- Replace weak verbs with stronger accurate verbs
- Reduce redundancy
- Improve bullet parallelism and consistency
- Reorder bullets for relevance to the target role
- Lightly align terminology to the target job posting, but only when truthful
- Split overly long bullets
- Merge repetitive bullets only if no meaning is lost

STYLE RULES:
- Keep the original structure: header + bullet list
- Keep approximately the same number of bullets unless combining duplicates improves clarity
- Prefer concise, high-signal bullets
- Use strong but honest action verbs
- Keep tone credible and senior
- Avoid generic corporate fluff
- Avoid vague filler like "results-driven," "dynamic," "passionate," or "team player"
- Avoid exaggerated claims
- Preserve technical specificity where it adds value

TARGET JOB POSTING USE:
- Prioritize bullets most relevant to the job posting
- Use the employer's terminology only when it accurately maps to the original experience
- Do not force keyword stuffing
- Do not rewrite the experience to fit the job if the source does not support it

OUTPUT REQUIREMENTS:
Return only the rewritten work experience entry.
Preserve this format:
- First line: Job Title, Company, Date Range
- Then bullet points
No commentary.
No explanations.
No notes.
No markdown fences.

SOURCE WORK EXPERIENCE ENTRY:
{block.text}

TARGET JOB POSTING:
{job_posting_text}"""

    try:
        if isinstance(llm_client, OpenAIClient):
            response = llm_client.client.chat.completions.create(
                model=llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            improved_text = response.choices[0].message.content
        else:
            improved_text = block.text

        return ImproveBlockResponse(
            improved_text=improved_text.strip(),
            original_text=block.text,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to align block: {str(e)}")


@app.get("/templates", response_model=list[TemplateInfo])
def list_templates(db: Session = Depends(get_db)) -> list[TemplateInfo]:
    """List available resume templates."""
    service = ExportService(db)
    templates = service.list_templates()
    return [TemplateInfo(**t) for t in templates]


@app.post("/export")
def export_resume(payload: ExportRequest, db: Session = Depends(get_db)) -> Response:
    """Export a resume as PDF or DOCX."""
    service = ExportService(db)
    fmt = payload.format.lower()
    if fmt not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'docx'")

    try:
        if fmt == "pdf":
            data = service.render_pdf(
                payload.job_id, payload.block_ids, payload.template, payload.resume_version
            )
            media_type = "application/pdf"
            ext = "pdf"
        else:
            data = service.render_docx(
                payload.job_id, payload.block_ids, payload.template, payload.resume_version
            )
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ext = "docx"
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = f"resume_{payload.resume_version}.{ext}"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/blocks")
def delete_all_blocks(db: Session = Depends(get_db)) -> dict:
    """Delete all resume blocks."""
    count = db.query(models.ResumeBlock).count()
    db.query(models.ResumeBlock).delete()
    db.commit()

    return {"deleted_count": count, "message": f"Deleted {count} resume blocks"}


# Mount static files AFTER all API routes to avoid conflicts
frontend_dir = Path(__file__).parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir / "static")), name="static")
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
