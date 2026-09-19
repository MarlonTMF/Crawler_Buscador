"""Contingency resolution for failed source URLs."""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import requests

from crawler.core.fetcher import HttpFetcher

logger = logging.getLogger(__name__)


@dataclass
class ContingencyResult:
    success: bool
    status_code: int
    resolved_url: Optional[str] = None
    content_bytes: Optional[bytes] = None
    method: str = "none"


class ContingencyEngine:
    """Attempts mirror/snapshot recovery after 4xx/5xx/timeout failures."""

    def __init__(self, fetcher: HttpFetcher, timeout: int = 3):
        self.fetcher = fetcher
        self.timeout = timeout
        self._wayback_rate_limited = False

    def latest_wayback_snapshot(self, url: str) -> Optional[str]:
        # 1. Intentar API de disponibilidad si no hay rate limiting activo
        if not self._wayback_rate_limited:
            api = "https://archive.org/wayback/available"
            try:
                response = requests.get(api, params={"url": url}, timeout=self.timeout)
                if response.status_code == 429:
                    self._wayback_rate_limited = True
                    logger.warning("Wayback availability devolvió 429; activando fallback de gateway directo.")
                elif response.status_code == 200:
                    data = response.json()
                    snapshot = data.get("archived_snapshots", {}).get("closest", {})
                    if snapshot.get("available") and snapshot.get("url"):
                        return snapshot["url"]
            except Exception as exc:
                if "429" in str(exc):
                    self._wayback_rate_limited = True
                logger.debug("Wayback availability lookup failed for %s: %s", url, exc)

        # 2. Fallback de gateway directo: web.archive.org/web/{timestamp}id_/{target_url}
        # Permite resolver snapshots aún si la API /available de archive.org tiene 429 o intermitencias
        m = re.search(r'/(20\d{2})/', url)
        year = m.group(1) if m else ""
        timestamp = f"{year}1231235959" if year else "2"

        base_candidates = [url]
        if url.startswith("https://"):
            base_candidates.append(url.replace("https://", "http://", 1))
        elif url.startswith("http://"):
            base_candidates.append(url.replace("http://", "https://", 1))

        candidates = []
        for c in base_candidates:
            candidates.append(c)
            if "://www." in c:
                candidates.append(c.replace("://www.", "://", 1))
            elif "://" in c:
                candidates.append(c.replace("://", "://www.", 1))
        seen = set()
        unique_candidates = [c for c in candidates if not (c in seen or seen.add(c))]

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        for target in unique_candidates:
            gateway_url = f"https://web.archive.org/web/{timestamp}id_/{target}"
            try:
                res = requests.head(gateway_url, headers=headers, timeout=8, allow_redirects=True)
                if res.status_code == 200:
                    cl = res.headers.get("content-length")
                    if cl is None or int(cl) > 1000:
                        return res.url or gateway_url
            except Exception:
                pass

        return None

    def fetch_bytes_with_fallback(self, url: str) -> ContingencyResult:
        success, status, content = self.fetcher.fetch_bytes(url)
        if success and content is not None:
            return ContingencyResult(True, status, url, content, "primary")

        if status not in {0, 403, 404, 408, 429, 500, 502, 503, 504}:
            return ContingencyResult(False, status, url, None, "primary_failed")

        snapshot_url = self.latest_wayback_snapshot(url)
        if not snapshot_url:
            return ContingencyResult(False, status, url, None, "no_snapshot")

        wb_success, wb_status, wb_content = self.fetcher.fetch_bytes(snapshot_url)
        return ContingencyResult(
            success=wb_success and wb_content is not None,
            status_code=wb_status,
            resolved_url=snapshot_url,
            content_bytes=wb_content,
            method="wayback_snapshot" if wb_success else "wayback_failed",
        )
