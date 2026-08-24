"""Contingency resolution for failed source URLs."""

import logging
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

    def __init__(self, fetcher: HttpFetcher, timeout: int = 15):
        self.fetcher = fetcher
        self.timeout = timeout

    def latest_wayback_snapshot(self, url: str) -> Optional[str]:
        api = "https://archive.org/wayback/available"
        try:
            response = requests.get(api, params={"url": url}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Wayback availability lookup failed for %s: %s", url, exc)
            return None

        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available") and snapshot.get("url"):
            return snapshot["url"]
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
