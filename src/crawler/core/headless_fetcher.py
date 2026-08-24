"""Optional Playwright-based fetcher with network response interception."""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class HeadlessFetchResult:
    html: str
    network_urls: List[str] = field(default_factory=list)


class HeadlessFetcher:
    """Renders dynamic pages when Playwright is installed."""

    def __init__(self, timeout_ms: int = 30000, scroll_steps: int = 3):
        self.timeout_ms = timeout_ms
        self.scroll_steps = scroll_steps

    def fetch(self, url: str) -> Tuple[bool, int, Optional[HeadlessFetchResult]]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            logger.warning("Playwright is not installed; headless fetcher is unavailable.")
            return False, 0, None

        network_urls: List[str] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.on("response", lambda response: network_urls.append(response.url))
                response = page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                for _ in range(self.scroll_steps):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(500)
                html = page.content()
                status = response.status if response else 200
                browser.close()
                return True, status, HeadlessFetchResult(html=html, network_urls=network_urls)
        except Exception as exc:
            logger.warning("Headless fetch failed for %s: %s", url, exc)
            return False, 0, None
