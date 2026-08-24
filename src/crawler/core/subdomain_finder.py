"""
Discover subdomains via Certificate Transparency (crt.sh).
Lightweight scaffold that queries crt.sh JSON output and extracts unique hostnames.
"""
import requests
from typing import List
import logging
import time

logger = logging.getLogger(__name__)


def find_subdomains(domain: str, timeout: int = 15, max_retries: int = 3, backoff: float = 1.5) -> List[str]:
    """Query crt.sh for certificates related to domain and extract subdomains.

    Performs retries with exponential backoff and a fallback query if the wildcard
    query returns server errors.

    Args:
        domain: base domain (e.g., 'finrural.org.bo')

    Returns:
        List of discovered subdomains (may include the base domain).
    """
    wildcard_url = f"https://crt.sh/?q=%25.{domain}&output=json"
    fallback_url = f"https://crt.sh/?q={domain}&output=json"

    data = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(wildcard_url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            logger.warning(f"crt.sh wildcard query attempt {attempt} failed for {domain}: {e}")
            if attempt < max_retries:
                time.sleep(backoff * attempt)
                continue
            # try fallback once
            try:
                resp = requests.get(fallback_url, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e2:
                logger.warning(f"crt.sh fallback query also failed for {domain}: {e2}")
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
