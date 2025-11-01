from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import yaml

from backend.db.session import get_session, init_db
from backend.models import models
from backend.services.prefill import PrefillPlanner
from backend.services.capture import CaptureService
from backend.services.tailor import TailorService
from backend.services.intake import IntakeService
from backend.services.submission import SubmissionLogger
from backend.services.artifacts import ArtifactManager
from backend.browser.prefill import run_prefill

app = typer.Typer(help="Job Ace CLI")


@app.command()
def init() -> None:
    """Initialise the database."""
    init_db()
    typer.echo("Database initialised")


@app.command()
def load_blocks(path: Path) -> None:
    """Load resume blocks from a YAML file."""
    if not path.exists():
        raise typer.Exit(code=1)
    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or []

    with get_session() as session:
        for item in content:
            block = models.ResumeBlock(
                category=item.get("category"),
                tags=",".join(item.get("tags", [])),
                text=item.get("text", ""),
            )
            session.add(block)
        typer.echo(f"Loaded {len(content)} blocks")


@app.command()
def intake(url: str, force: bool = typer.Option(False, help="Re-run intake even if exists")) -> None:
    """Run intake for a job posting."""
    with get_session() as session:
        service = IntakeService(session)
        job_posting = service.run(url, force)
        artifact_dir = ArtifactManager(session).ensure_job_dir(job_posting)
        typer.echo(json.dumps({"job_id": job_posting.id, "artifact_dir": str(artifact_dir)}, indent=2))


@app.command()
def tailor(job_id: int, block_ids: str, resume_version: str = "v1") -> None:
    """Tailor resume using comma-separated block IDs."""
    block_list = [int(b.strip()) for b in block_ids.split(",") if b.strip()]
    with get_session() as session:
        service = TailorService(session)
        result = service.run(job_id, block_list, resume_version)
        typer.echo(json.dumps(result, indent=2))


@app.command()
def prefill_plan(job_id: int) -> None:
    with get_session() as session:
        planner = PrefillPlanner(session)
        plan = planner.build_plan(job_id)
    typer.echo(json.dumps(plan, indent=2))


@app.command()
def apply(prefill_path: Path) -> None:
    result = run_prefill(prefill_path)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def capture(job_id: int, headless: bool = typer.Option(True, help="Run browser headless")) -> None:
    """Capture form schema and screenshots for a job posting."""
    with get_session() as session:
        service = CaptureService(session)
        summary = service.run(job_id, headless=headless)
        typer.echo(json.dumps(summary, indent=2))


@app.command()
def log_submit(
    job_id: int,
    confirmation_id: Optional[str] = typer.Option(None),
    confirmation_text: Optional[str] = typer.Option(None),
    screenshot_path: Optional[Path] = typer.Option(None),
) -> None:
    with get_session() as session:
        logger = SubmissionLogger(session)
        application = logger.log(
            job_id,
            confirmation_id,
            confirmation_text,
            str(screenshot_path) if screenshot_path else None,
        )
        typer.echo(json.dumps({
            "application_id": application.id,
            "status": application.status,
            "applied_at": application.applied_at.isoformat() if application.applied_at else None,
        }, indent=2))


def run() -> None:
    app()


if __name__ == "__main__":
    run()
