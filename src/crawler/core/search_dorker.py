"""Programmatic search dorking helpers.

The module is intentionally provider-light: it supports Bing Web Search and
Google Custom Search when API keys are provided in YAML or environment
variables, and otherwise returns no results without failing the crawl.
"""

import logging
import os
from typing import Any, Dict, Iterable, List, Optional

import requests

logger = logging.getLogger(__name__)


class SearchDorker:
    """Runs document-focused search queries through configured search APIs."""

    def __init__(
        self,
        provider: str = "none",
        api_key: Optional[str] = None,
        cx: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: int = 15,
        max_results: int = 50,
    ):
        self.provider = provider.lower()
        self.api_key = api_key
        self.cx = cx
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_results = max_results

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "SearchDorker":
        cfg = config.get("search_dorking", {})
        provider = cfg.get("provider", os.getenv("SEARCH_DORKER_PROVIDER", "none"))
        api_key = cfg.get("api_key") or os.getenv("BING_SEARCH_API_KEY") or os.getenv("GOOGLE_SEARCH_API_KEY")
        cx = cfg.get("cx") or os.getenv("GOOGLE_SEARCH_CX")
        endpoint = cfg.get("endpoint")
        return cls(
            provider=provider,
            api_key=api_key,
            cx=cx,
            endpoint=endpoint,
            timeout=int(cfg.get("timeout", 15)),
            max_results=int(cfg.get("max_results", 50)),
        )

    @staticmethod
    def build_queries(domain: str, file_types: Iterable[str]) -> List[str]:
        keywords = '("reporte" OR "boletin" OR "boletín" OR "estadistica" OR "estadística" OR "memoria" OR "informe")'
        return [f"site:{domain} filetype:{ext.strip('.')} {keywords}" for ext in file_types]

    def search_domain_documents(self, domain: str, file_types: Iterable[str]) -> List[str]:
        if self.provider in {"none", "", "disabled"}:
            logger.info("Search dorking disabled; set search_dorking.provider to enable it.")
            return []
        if not self.api_key:
            logger.warning("Search dorking provider '%s' has no API key configured.", self.provider)
            return []

        urls: List[str] = []
        for query in self.build_queries(domain, file_types):
            if len(urls) >= self.max_results:
                break
            if self.provider == "bing":
                urls.extend(self._search_bing(query))
            elif self.provider == "google":
                urls.extend(self._search_google(query))
            else:
                logger.warning("Unsupported search dorking provider: %s", self.provider)
                break

        seen = set()
        unique = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique[: self.max_results]

    def _search_bing(self, query: str) -> List[str]:
        endpoint = self.endpoint or "https://api.bing.microsoft.com/v7.0/search"
        try:
            response = requests.get(
                endpoint,
                params={"q": query, "count": min(50, self.max_results)},
                headers={"Ocp-Apim-Subscription-Key": self.api_key or ""},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return [item.get("url") for item in data.get("webPages", {}).get("value", []) if item.get("url")]
        except Exception as exc:
            logger.warning("Bing search dork failed: %s", exc)
            return []

    def _search_google(self, query: str) -> List[str]:
        if not self.cx:
            logger.warning("Google search dorking needs a Custom Search cx value.")
            return []
        endpoint = self.endpoint or "https://www.googleapis.com/customsearch/v1"
        try:
            response = requests.get(
                endpoint,
                params={"q": query, "key": self.api_key, "cx": self.cx, "num": 10},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return [item.get("link") for item in data.get("items", []) if item.get("link")]
        except Exception as exc:
            logger.warning("Google search dork failed: %s", exc)
            return []
