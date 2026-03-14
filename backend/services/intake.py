from __future__ import annotations

import logging
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import models
from backend.services.artifacts import ArtifactManager
from backend.services.llm import BaseLLMClient, get_llm_client
from backend.config import get_settings

logger = logging.getLogger(__name__)


class IntakeService:
    def __init__(self, db: Session, llm: BaseLLMClient | None = None):
        self.db = db
        self.artifacts = ArtifactManager(db)
        self.settings = get_settings()
        self.llm = llm or get_llm_client(self.settings, task="extraction")

    def run(self, url: str, force: bool = False) -> models.JobPosting:
        existing = self.db.scalar(select(models.JobPosting).where(models.JobPosting.url == url))
        if existing and not force:
            logger.info("Job posting already exists", extra={"job_id": existing.id})
            return existing

        html = self._fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        extraction = self.llm.extract_job_json(text)
        company_name = extraction.company or self._guess_company_from_url(url)
        company = self._get_or_create_company(company_name)

        if existing:
            job_posting = existing
        else:
            job_posting = models.JobPosting(company_id=company.id, url=url)
            self.db.add(job_posting)
            self.db.flush()  # assign id
            application = models.Application(job_posting_id=job_posting.id)
            self.db.add(application)
            self.db.flush()
            job_posting.application = application

        job_posting.title = extraction.title
        job_posting.location = extraction.location
        job_posting.employment_type = extraction.employment_type
        job_posting.seniority = extraction.seniority
        job_posting.salary_min = extraction.salary_min
        job_posting.salary_max = extraction.salary_max
        job_posting.deadline = extraction.deadline
        job_posting.portal_hint = extraction.portal_hint
        job_posting.apply_url = extraction.apply_url or url
        job_posting.must_haves_json = self._dumps(extraction.must_haves)
        job_posting.nice_to_haves_json = self._dumps(extraction.nice_to_haves)
        job_posting.screening_questions_json = self._dumps(extraction.screening_questions)
        job_posting.status = "intake"
        self.db.flush()

        html_path = self.artifacts.write_text(job_posting, "posting_html", "raw/posting.html", html)
        text_path = self.artifacts.write_text(job_posting, "posting_text", "raw/posting.txt", text)
        pdf_path = self._write_pdf_placeholder(job_posting, text)
        jd_json_path = self.artifacts.write_text(
            job_posting,
            "jd_json",
            "derived/jd.json",
            extraction.to_json(),
        )

        job_posting.captured_html_path = str(html_path)
        job_posting.captured_pdf_path = str(pdf_path)
        job_posting.jd_json_path = str(jd_json_path)
        self.db.flush()

        return job_posting

    def _fetch_html(self, url: str) -> str:
        logger.info("Fetching job posting", extra={"url": url, "method": "httpx"})
        headers = self._http_headers()
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
                if resp.status_code < 400:
                    logger.info(
                        "Fetched job posting",
                        extra={"url": url, "source": "httpx", "status": resp.status_code},
                    )
                    return resp.text
                logger.warning(
                    "HTTP fetch returned status",
                    extra={"url": url, "status": resp.status_code},
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "HTTP fetch failed, falling back to browser",
                extra={"url": url, "error": str(exc)},
            )

        return self._fetch_via_playwright(url)

    def _fetch_via_playwright(self, url: str) -> str:
        logger.info("Fetching job posting via Playwright", extra={"url": url})
        headers = self._http_headers()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=self.settings.playwright_headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=headers["User-Agent"],
                viewport={"width": 1280, "height": 880},
                locale="en-US",
                extra_http_headers={k: v for k, v in headers.items() if k.lower() != "user-agent"},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:  # PlaywrightTimeoutError
                logger.warning("Network idle wait timed out", extra={"url": url})
            html = page.content()
            context.close()
            browser.close()
        logger.info("Fetched job posting via Playwright", extra={"url": url, "source": "playwright"})
        return html

    def _http_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.settings.intake_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://www.google.com/",
        }

    def _get_or_create_company(self, company_name: str | None) -> models.Company:
        name = company_name or "Unknown"
        company = self.db.scalar(select(models.Company).where(models.Company.name == name))
        if company:
            return company
        company = models.Company(name=name)
        self.db.add(company)
        self.db.flush()
        return company

    def _write_pdf_placeholder(self, job_posting: models.JobPosting, text: str) -> Path:
        content = f"Job posting snapshot placeholder for {job_posting.title or 'role'}\n\n{text[:2000]}"
        return self.artifacts.write_bytes(
            job_posting,
            kind="posting_pdf",
            relative_path="raw/posting.pdf",
            content=content.encode("utf-8"),
        )

    @staticmethod
    def _dumps(values: list[str]) -> str:
        import json

        return json.dumps(values, ensure_ascii=False)

    @staticmethod
    def _guess_company_from_url(url: str) -> str:
        host_parts = url.split("//")[-1].split("/")[0].split(".")
        if len(host_parts) >= 2:
            return host_parts[-2].capitalize()
        return host_parts[0].capitalize() if host_parts else "Unknown"
