from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - fallback when Playwright not installed
    sync_playwright = None


@dataclass(slots=True)
class BrowserCapture:
    """Bundle of artefacts extracted from a job detail page."""

    url: str
    html: str
    text: str
    screenshot: Optional[bytes]
    metadata: Dict[str, Any]


class JobPageAnalyzer:
    """Obtain a canonical HTML/Text snapshot for downstream parsing.

    The class prefers a real browser (Playwright) to ensure dynamic content is reflected. If
    Playwright is unavailable or errors out, it falls back to an HTTP GET. The fallback keeps the
    pipeline operational in headless environments and tests.
    """

    def __init__(self, *, user_agent: Optional[str] = None, http_timeout: float = 20.0) -> None:
        self.user_agent = user_agent
        self.http_timeout = http_timeout

    def capture(self, url: str, *, wait_until: str = "networkidle", force_playwright: bool = False) -> BrowserCapture:
        """Return a `BrowserCapture` bundle for the supplied URL.

        When `force_playwright` is False (default), the method will use HTTP fallback if launching a
        browser fails. Tests rely on this behaviour to avoid real browser launches.
        """

        if sync_playwright and (force_playwright or self._should_use_playwright()):
            try:
                return self._from_playwright(url, wait_until=wait_until)
            except Exception as exc:  # pragma: no cover - execution requires browser context
                logger.warning("Playwright capture failed; falling back to HTTP", exc_info=exc)

        html = self._fetch_http(url)
        text = self._html_to_text(html)
        metadata = {"source": "httpx", "wait_until": None}
        return BrowserCapture(url=url, html=html, text=text, screenshot=None, metadata=metadata)

    @staticmethod
    def _should_use_playwright() -> bool:
        return bool(sync_playwright)

    def _from_playwright(self, url: str, *, wait_until: str) -> BrowserCapture:
        if not sync_playwright:  # pragma: no cover - defensive guard
            raise RuntimeError("Playwright not available")

        with sync_playwright() as playwright:  # pragma: no cover - requires browser runtime
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1440, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until=wait_until)
            html = page.content()
            text = page.inner_text("body")
            screenshot_bytes = page.screenshot(full_page=True)
            metadata = {
                "source": "playwright",
                "wait_until": wait_until,
                "viewport": context.viewport_size,
            }
            context.close()
            browser.close()

        return BrowserCapture(
            url=url,
            html=html,
            text=text,
            screenshot=screenshot_bytes,
            metadata=metadata,
        )

    def _fetch_http(self, url: str) -> str:
        headers = {"User-Agent": self.user_agent} if self.user_agent else None
        with httpx.Client(timeout=self.http_timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    @staticmethod
    def _html_to_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text("\n", strip=True)

