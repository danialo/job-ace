"""End-to-end Playwright tests for the Job Ace web UI."""
import re

import pytest
from playwright.sync_api import Page, expect

from backend.models import models

pytestmark = pytest.mark.e2e


# --- Page load and navigation ---

def test_page_loads(page: Page, live_server):
    page.goto(live_server)
    expect(page).to_have_title("Job Ace - Application Assistant")


def test_header_visible(page: Page, live_server):
    page.goto(live_server)
    expect(page.locator("h1")).to_contain_text("Job Ace")


def test_tabs_present(page: Page, live_server):
    page.goto(live_server)
    tabs = page.locator(".tab-button")
    expect(tabs).to_have_count(5)


def test_tab_switching(page: Page, live_server):
    page.goto(live_server)

    # Click "Capture Job" tab
    page.click('[data-tab="intake"]')
    expect(page.locator("#intake")).to_be_visible()
    expect(page.locator("#resume")).to_be_hidden()

    # Click "Tailor Resume" tab
    page.click('[data-tab="tailor"]')
    expect(page.locator("#tailor")).to_be_visible()
    expect(page.locator("#intake")).to_be_hidden()

    # Click "Apply" tab
    page.click('[data-tab="apply"]')
    expect(page.locator("#apply")).to_be_visible()

    # Click back to "Resume Intake"
    page.click('[data-tab="resume"]')
    expect(page.locator("#resume")).to_be_visible()


def test_default_tab_is_resume(page: Page, live_server):
    page.goto(live_server)
    expect(page.locator("#resume")).to_be_visible()
    expect(page.locator('[data-tab="resume"]')).to_have_class(re.compile("active"))


# --- Resume Intake tab ---

def test_resume_upload_form_present(page: Page, live_server):
    page.goto(live_server)
    expect(page.locator("#resume-file")).to_be_visible()
    expect(page.locator('#upload-resume-form button[type="submit"]')).to_be_visible()


def test_resume_upload_accepts_file_types(page: Page, live_server):
    page.goto(live_server)
    file_input = page.locator("#resume-file")
    expect(file_input).to_have_attribute("accept", ".pdf,.docx,.doc,.txt")


# --- Capture Job tab ---

def test_intake_form_present(page: Page, live_server):
    page.goto(live_server)
    page.click('[data-tab="intake"]')
    expect(page.locator("#job-url")).to_be_visible()
    expect(page.locator("#force-refresh")).to_be_visible()
    expect(page.locator('#intake-form button[type="submit"]')).to_be_visible()


def test_jobs_list_empty_state(page: Page, live_server):
    page.goto(live_server)
    page.click('[data-tab="intake"]')
    expect(page.locator("#jobs-list")).to_contain_text("No jobs captured yet")


# --- Tailor Resume tab ---

def test_tailor_form_present(page: Page, live_server):
    page.goto(live_server)
    page.click('[data-tab="tailor"]')
    expect(page.locator("#select-job")).to_be_visible()
    expect(page.locator("#block-selector")).to_be_visible()
    expect(page.locator('#tailor-form button[type="submit"]')).to_be_visible()


def test_block_selector_empty_state(page: Page, live_server):
    page.goto(live_server)
    page.click('[data-tab="tailor"]')
    expect(page.locator("#block-selector")).to_contain_text("No blocks available")


# --- Apply tab ---

def test_apply_form_present(page: Page, live_server):
    page.goto(live_server)
    page.click('[data-tab="apply"]')
    expect(page.locator("#submit-job")).to_be_visible()
    expect(page.locator("#confirmation-id")).to_be_visible()
    expect(page.locator("#confirmation-text")).to_be_visible()
    expect(page.locator('#submit-form button[type="submit"]')).to_be_visible()


def test_applications_list_empty_state(page: Page, live_server):
    page.goto(live_server)
    page.click('[data-tab="apply"]')
    expect(page.locator("#applications-list")).to_contain_text("No applications logged yet")


# --- Footer / API status ---

def test_footer_visible(page: Page, live_server):
    page.goto(live_server)
    expect(page.locator("footer")).to_contain_text("Job Ace v0.1.0")


# --- Data-driven tests (with seeded data) ---

def test_jobs_list_shows_seeded_job(page: Page, live_server, e2e_session):
    company = models.Company(name="E2ECo")
    e2e_session.add(company)
    e2e_session.flush()
    job = models.JobPosting(company_id=company.id, url="https://e2e.test/job", title="E2E Engineer")
    e2e_session.add(job)
    e2e_session.commit()

    page.goto(live_server)
    page.click('[data-tab="intake"]')
    page.wait_for_timeout(500)

    expect(page.locator("#jobs-list")).to_contain_text("E2E Engineer")


def test_blocks_api_roundtrip(live_server):
    """Confirm blocks via API, then verify they come back from the list endpoint."""
    import httpx

    # Confirm blocks via API
    resp = httpx.post(
        f"{live_server}/confirm-resume-blocks",
        json={
            "blocks": [
                {"category": "summary", "tags": ["python"], "content": "E2E test block content"},
            ]
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["blocks_saved"] == 1

    # Verify blocks come back from list endpoint
    resp = httpx.get(f"{live_server}/blocks")
    assert resp.status_code == 200
    blocks = resp.json()
    assert any(b["category"] == "summary" for b in blocks)


def test_reset_data_button(page: Page, live_server):
    page.goto(live_server)
    reset_btn = page.locator("#reset-data-btn")
    expect(reset_btn).to_be_visible()
