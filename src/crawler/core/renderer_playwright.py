"""Playwright-based renderer to capture page screenshots and PDFs.

This module is optional and only imported when `use_playwright_ocr` is enabled in config.
It attempts to import `playwright.sync_api` at runtime and fails gracefully when not available.
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except Exception as e:
        logger.warning("Playwright not available: %s", e)
        return None


class PlaywrightRenderer:
    def __init__(self, headless: bool = True, viewport: Optional[dict] = None):
        self._sync_playwright = _import_playwright()
        self.headless = headless
        self.viewport = viewport or {"width": 1280, "height": 800}

    def available(self) -> bool:
        return self._sync_playwright is not None

    def screenshot(self, url: str, output_path: str) -> bool:
        if not self.available():
            return False
        with self._sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page(viewport=self.viewport)
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.screenshot(path=output_path, full_page=True)
            browser.close()
        return True

    def pdf(self, url: str, output_path: str) -> bool:
        if not self.available():
            return False
        with self._sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page(viewport=self.viewport)
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.pdf(path=output_path)
            browser.close()
        return True
