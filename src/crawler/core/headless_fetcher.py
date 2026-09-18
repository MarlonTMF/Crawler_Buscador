"""Optional Playwright-based fetcher with network response interception."""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class HeadlessFetchResult:
    html: str
    network_urls: List[str] = field(default_factory=list)
    # Igual que network_urls pero con status/content-type, usado por api_detector
    # para distinguir llamadas de API (JSON/XHR) del resto del tráfico (imágenes, CSS...).
    network_responses: List[dict] = field(default_factory=list)


class HeadlessFetcher:
    """Renders dynamic pages when Playwright is installed."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        timeout_ms: int = 30000,
        scroll_steps: int = 3,
        wait_until: str = "domcontentloaded",
        user_agent: Optional[str] = None,
    ):
        self.timeout_ms = timeout_ms
        self.scroll_steps = scroll_steps
        self.wait_until = wait_until
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

    def fetch(self, url: str) -> Tuple[bool, int, Optional[HeadlessFetchResult]]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            logger.warning("Playwright is not installed; headless fetcher is unavailable.")
            return False, 0, None

        network_urls: List[str] = []
        network_responses: List[dict] = []

        def _on_response(response):
            network_urls.append(response.url)
            try:
                network_responses.append({
                    "url": response.url,
                    "status": response.status,
                    "content_type": response.headers.get("content-type"),
                })
            except Exception:
                # Playwright puede fallar al leer headers de respuestas ya cerradas.
                pass

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(user_agent=self.user_agent)
                    page = context.new_page()
                    page.on("response", _on_response)
                    response = page.goto(url, wait_until=self.wait_until, timeout=self.timeout_ms)
                    for _ in range(self.scroll_steps):
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(500)
                    html = page.content()
                    status = response.status if response else 200
                    return True, status, HeadlessFetchResult(
                        html=html, network_urls=network_urls, network_responses=network_responses,
                    )
                finally:
                    browser.close()
        except Exception as exc:
            logger.warning("Headless fetch failed for %s: %s", url, exc)
            return False, 0, None
