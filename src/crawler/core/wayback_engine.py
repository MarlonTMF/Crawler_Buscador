"""
Simple Wayback CDX API helper to discover historical URLs for a domain.
This is a lightweight scaffold: it fetches CDX entries and returns unique original URLs.
"""
from typing import List
import requests
import logging
import time

logger = logging.getLogger(__name__)


def query_wayback_urls(domain: str, file_types: List[str] = None, limit: int = 1000, timeout: int = 15, max_retries: int = 3, backoff: float = 1.5) -> List[str]:
    """Query the Wayback CDX API for the given domain and return a list of original URLs.

    Args:
        domain: base domain to query (e.g., 'finrural.org.bo')
        file_types: optional list of file extensions to filter by (['pdf','xlsx'])
        limit: maximum number of results

    Returns:
        List of unique URLs discovered in Wayback CDX.
    """
    if file_types is None:
        file_types = ["pdf", "xlsx", "csv", "zip"]

    base = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": f"{domain}/*",
        "output": "json",
        "fl": "original,statuscode,mimetype",
        "filter": "statuscode:200",
        "limit": str(limit),
        "showResumeKey": "true"
    }

    data = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(base, params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            logger.warning(f"Wayback CDX query attempt {attempt} failed for {domain}: {e}")
            if attempt < max_retries:
                time.sleep(backoff * attempt)
            else:
                return []

    urls = []
    # first row may be header
    for row in data[1:] if len(data) > 1 else []:
        original = row[0]
        mimetype = row[2] if len(row) > 2 else ""
        lower = original.lower()
        for ext in file_types:
            if lower.endswith(f".{ext}") or (ext in mimetype.lower()):
                urls.append(original)
                break

    # deduplicate preserving order
    seen = set()
    result = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)

    return result
