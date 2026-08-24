"""Sitemap discovery utilities built around the existing fetcher contract."""

import logging
import xml.etree.ElementTree as ET
from typing import List, Set
from urllib.parse import urljoin, urlparse

from crawler.core.fetcher import HttpFetcher

logger = logging.getLogger(__name__)


def _xml_urls(xml_text: str) -> List[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    urls = []
    for elem in root.iter():
        if elem.tag.lower().endswith("loc") and elem.text:
            urls.append(elem.text.strip())
    return urls


def discover_sitemap_urls(seed_url: str, fetcher: HttpFetcher, max_sitemaps: int = 10) -> List[str]:
    """Finds URLs listed in sitemap.xml or robots.txt sitemap declarations."""
    parsed = urlparse(seed_url)
    if not parsed.scheme or not parsed.netloc:
        return []

    base = f"{parsed.scheme}://{parsed.netloc}"
    sitemap_candidates: Set[str] = {urljoin(base, "/sitemap.xml")}

    ok, _, robots_text = fetcher.fetch_html(urljoin(base, "/robots.txt"))
    if ok and robots_text:
        for line in robots_text.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_candidates.add(line.split(":", 1)[1].strip())

    discovered: List[str] = []
    for sitemap_url in list(sitemap_candidates)[:max_sitemaps]:
        ok, _, xml_text = fetcher.fetch_html(sitemap_url)
        if not ok or not xml_text:
            continue
        for loc in _xml_urls(xml_text):
            if loc.endswith(".xml") and len(sitemap_candidates) < max_sitemaps:
                sitemap_candidates.add(loc)
            else:
                discovered.append(loc)

    return list(dict.fromkeys(discovered))
