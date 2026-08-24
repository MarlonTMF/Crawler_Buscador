"""
Async HTTP fetcher scaffold using httpx.AsyncClient.
Provides simple async fetch_html and fetch_bytes utilities.
"""
from typing import Tuple, Optional
import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)


class AsyncFetcher:
    def __init__(self, timeout: int = 15, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def fetch_html(self, url: str) -> Tuple[bool, int, Optional[str]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        r.encoding = r.apparent_encoding or 'utf-8'
                        return True, r.status_code, r.text
                    return False, r.status_code, None
                except Exception as e:
                    logger.warning(f"Async GET {url} attempt {attempt} failed: {e}")
                    await asyncio.sleep(1.5 * attempt)
        return False, 0, None

    async def fetch_bytes(self, url: str) -> Tuple[bool, int, Optional[bytes]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return True, r.status_code, r.content
                    return False, r.status_code, None
                except Exception as e:
                    logger.warning(f"Async GET bytes {url} attempt {attempt} failed: {e}")
                    await asyncio.sleep(1.5 * attempt)
        return False, 0, None

    async def fetch_head(self, url: str) -> Tuple[bool, int, dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    # httpx uses `follow_redirects` for following redirects
                    r = await client.head(url, follow_redirects=True)
                    status = r.status_code
                    # normalize headers to lower-case keys
                    headers = {k.lower(): v for k, v in r.headers.items()}
                    allowed = (200 <= status <= 206)
                    return allowed, status, headers
                except Exception as e:
                    logger.warning(f"Async HEAD {url} attempt {attempt} failed: {e}")
                    await asyncio.sleep(1.5 * attempt)
        return False, 0, {}

    # sync convenience wrappers
    def fetch_html_sync(self, url: str):
        return asyncio.run(self.fetch_html(url))

    def fetch_bytes_sync(self, url: str):
        return asyncio.run(self.fetch_bytes(url))

    def fetch_head_sync(self, url: str):
        return asyncio.run(self.fetch_head(url))
