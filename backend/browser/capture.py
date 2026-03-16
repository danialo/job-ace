from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Locator, Page, sync_playwright


@dataclass
class CaptureResult:
    schema_path: Path
    raw_html_path: Path
    screenshots: List[Path]
    stage_count: int


def _stable_selector(page: Page, locator: Locator) -> str:
    handle = locator.element_handle()
    if not handle:
        return ""
    # Prefer data-qa/test ids, then name/id, else nth-of-type path
    attrs = [
        ("data-testid", handle.get_attribute("data-testid")),
        ("data-test", handle.get_attribute("data-test")),
        ("data-qa", handle.get_attribute("data-qa")),
        ("name", handle.get_attribute("name")),
        ("id", handle.get_attribute("id")),
    ]
    for k, v in attrs:
        if v:
            if k == "id":
                return f"#{v}"
            return f"[{k}='{v}']"
    # Fallback: role based
    role = handle.get_attribute("role")
    if role:
        return f"[role='{role}']"
    # Final fallback: CSS relative path from DOM
    # This is a heuristic and may be brittle; acceptable for MVP capture
    return locator.selector or "input,textarea,select"


def _field_type(input_type: Optional[str], tag: str) -> str:
    if tag == "textarea":
        return "textarea"
    if tag == "select":
        return "select"
    if input_type in {"email", "url", "date", "number", "file", "tel"}:
        mapping = {"tel": "phone"}
        return mapping.get(input_type, input_type)
    return "text"


def _extract_fields(page: Page) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    controls = page.locator("input, textarea, select").filter(has_not=page.locator('[type="hidden"]'))
    count = controls.count()
    for i in range(count):
        el = controls.nth(i)
        tag = el.evaluate("e => e.tagName.toLowerCase()")
        itype = el.get_attribute("type") or ""
        label_text = None
        # Try for= association
        el_id = el.get_attribute("id")
        if el_id:
            lab = page.locator(f"label[for='{el_id}']")
            if lab.count() > 0:
                label_text = lab.first.inner_text().strip() or None
        if not label_text:
            # Nearest label ancestor or aria-label
            aria = el.get_attribute("aria-label")
            if aria:
                label_text = aria
        selector = _stable_selector(page, el)
        required = el.get_attribute("required") is not None
        maxlength = el.get_attribute("maxlength")
        placeholder = el.get_attribute("placeholder")
        field: Dict[str, Any] = {
            "id": f"f{i}",
            "selector": selector,
            "label": label_text,
            "control": {
                "type": _field_type(itype, tag),
                "required": bool(required),
                "multiple": el.get_attribute("multiple") is not None,
                "maxlength": int(maxlength) if maxlength and maxlength.isdigit() else None,
                "placeholder": placeholder,
            },
        }
        if tag == "select":
            options = []
            opts = el.locator("option")
            for j in range(opts.count()):
                opt = opts.nth(j)
                options.append({
                    "value": opt.get_attribute("value") or "",
                    "label": (opt.inner_text() or "").strip() or None,
                })
            field["control"]["options"] = options
        fields.append(field)
    return fields


def capture_form(url: str, artifact_dir: Path, headless: bool = True) -> CaptureResult:
    raw_dir = artifact_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15000)

        html = page.content()
        raw_html_path = raw_dir / "form_original.html"
        raw_html_path.write_text(html, encoding="utf-8")

        fields = _extract_fields(page)
        stage = {
            "id": "stage-1",
            "name": "Application",
            "sequence": 1,
            "fields": fields or [],
        }
        screenshots: List[Path] = []
        shot_path = raw_dir / "stage_1.png"
        page.screenshot(path=str(shot_path), full_page=True)
        screenshots.append(shot_path)

        schema: Dict[str, Any] = {
            "schema_version": "1.0.0",
            "job_ref": {
                "job_id": None,
                "source_url": url,
                "portal_family": None,
                "capture_run_id": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            },
            "capture": {
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "browser": {"engine": "chromium", "headless": headless},
                "stages": [stage],
            },
            "artifacts": {
                "schema_path": str(raw_dir / "form_schema.json"),
                "screenshots": [{"stage": "stage-1", "path": str(shot_path), "description": "Initial capture"}],
                "raw_html_path": str(raw_html_path),
                "log_path": str(raw_dir / "capture_log.json"),
            },
        }

        schema_path = raw_dir / "form_schema.json"
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        (raw_dir / "capture_log.json").write_text(json.dumps({"field_count": len(fields)}), encoding="utf-8")

        context.close()
        browser.close()

    return CaptureResult(schema_path=schema_path, raw_html_path=raw_html_path, screenshots=screenshots, stage_count=1)

