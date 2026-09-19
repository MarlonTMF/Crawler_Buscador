"""
Simple Wayback CDX API helper to discover historical URLs for a domain.
This is a lightweight scaffold: it fetches CDX entries and returns unique original URLs.
"""
from typing import List
import requests
import logging
import time
from crawler.core.external_cache import cache_get, cache_set
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def query_wayback_urls(domain: str, file_types: List[str] = None, limit: int = 1000, timeout: int = 6, max_retries: int = 2, backoff: float = 1.0, cache_ttl: int = 86400) -> List[str]:
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

    # try cache first
    cached = cache_get("wayback", domain, cache_ttl)
    if cached is not None:
        return cached

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
                # cache negative result for a short period to avoid hammering
                cache_set("wayback", domain, [])
                return []

    urls = []
    # Data may include a header row or unexpected empty rows; iterate defensively.
    rows = data[1:] if isinstance(data, list) and len(data) > 1 else (data or [])
    for row in rows:
        if not row or not isinstance(row, (list, tuple)):
            continue
        if len(row) < 1:
            continue
        original = row[0]
        mimetype = row[2] if len(row) > 2 else ""
        lower = str(original).lower()
        for ext in file_types:
            if lower.endswith(f".{ext}") or (ext in str(mimetype).lower()):
                urls.append(original)
                break

    # deduplicate preserving order
    seen = set()
    result = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    cache_set("wayback", domain, result)
    return result


def _query_wayback_availability(domain: str, timeout: int = 10, max_retries: int = 2, backoff: float = 1.5) -> List[str]:
    """Use the Internet Archive 'wayback/available' API to find any snapshot for the domain.

    Returns a list of candidate original URLs (domain roots) where snapshots exist.
    """
    api = "https://archive.org/wayback/available?url="
    candidates = [f"https://{domain}/", f"http://{domain}/", f"https://www.{domain}/", f"http://www.{domain}/"]
    found = []
    for candidate in candidates:
        url = api + quote_plus(candidate)
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                snap = data.get("archived_snapshots", {}).get("closest")
                if snap and snap.get("available"):
                    # return the original candidate URL (not the archived URL)
                    found.append(candidate)
                break
            except Exception as e:
                logger.warning(f"Wayback availability attempt {attempt} failed for {candidate}: {e}")
                if attempt < max_retries:
                    time.sleep(backoff * attempt)
                    continue
                break

    # deduplicate
    return list(dict.fromkeys(found))
