"""
Discover subdomains via Certificate Transparency (crt.sh).
Lightweight scaffold that queries crt.sh JSON output and extracts unique hostnames.
"""
import requests
from typing import List
import logging

logger = logging.getLogger(__name__)


def find_subdomains(domain: str) -> List[str]:
    """Query crt.sh for certificates related to domain and extract subdomains.

    Args:
        domain: base domain (e.g., 'finrural.org.bo')

    Returns:
        List of discovered subdomains (may include the base domain).
    """
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"crt.sh query failed for {domain}: {e}")
        return []

    hosts = set()
    for item in data:
        name_value = item.get("name_value") or item.get("common_name")
        if not name_value:
            continue
        # name_value sometimes contains multiple names separated by newlines
        for part in str(name_value).split('\n'):
            part = part.strip()
            if part.endswith(domain):
                hosts.add(part.lower())

    return sorted(hosts)
