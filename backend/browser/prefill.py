from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.sync_api import sync_playwright


def run_prefill(prefill_path: Path) -> Dict[str, Optional[str]]:
    payload: Dict[str, Any] = json.loads(prefill_path.read_text(encoding="utf-8"))
    artifact_dir = Path(payload["artifact_dir"])

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, args=["--use-gl=desktop"])
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(payload["apply_url"], wait_until="domcontentloaded")

        for field in payload.get("fields", []):
            locator = page.locator(field["selector"])
            field_type = field.get("type", "text")
            if field_type == "select":
                locator.select_option(field["value"])
            elif field_type == "textarea":
                locator.fill(field["value"])
            else:
                locator.fill(field["value"])

        for upload in payload.get("uploads", []):
            page.set_input_files(upload["selector"], upload["path"])

        input(
            "Review the form, solve any captcha, and click Submit manually. Press Enter to capture proof..."
        )

        submission_dir = artifact_dir / "submission"
        submission_dir.mkdir(parents=True, exist_ok=True)
        proof_path = submission_dir / "submit_proof.png"
        page.screenshot(path=str(proof_path), full_page=True)

        confirmation_id = None
        confirmation_selector = payload.get("confirmation_selector")
        if confirmation_selector:
            locator = page.locator(confirmation_selector)
            if locator.count() > 0:
                confirmation_id = locator.first.inner_text().strip()

        context.close()
        browser.close()

    return {
        "confirmation_id": confirmation_id,
        "screenshot_path": str(proof_path),
    }
