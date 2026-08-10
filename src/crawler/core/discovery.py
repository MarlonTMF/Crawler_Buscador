"""
Motor de descubrimiento enfocado en Datasets (Dataset-First Discovery Engine).
Visita únicamente semillas registradas y páginas índice, filtrando URLs institucionales y extrayendo enlaces a archivos.
"""

import logging
from typing import List, Dict, Any, Set, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from crawler.core.fetcher import HttpFetcher
from crawler.sources.base_adapter import BaseSourceAdapter

logger = logging.getLogger(__name__)


class DiscoveredCandidate:
    """Representa un candidato a recurso descargable encontrado durante la fase de descubrimiento."""

    def __init__(
        self,
        url: str,
        url_origin: str,
        anchor_text: str,
        context_text: str,
        dataset_id: str,
        file_type: str
    ):
        self.url = url
        self.url_origin = url_origin
        self.anchor_text = anchor_text
        self.context_text = context_text
        self.dataset_id = dataset_id
        self.file_type = file_type


class DiscoveryEngine:
    """Navega páginas semillas de forma controlada y extrae enlaces descargables."""

    def __init__(self, fetcher: HttpFetcher, adapter: BaseSourceAdapter):
        self.fetcher = fetcher
        self.adapter = adapter
        self.visited_urls: Set[str] = set()

    def _is_download_link(self, href: str, text: str) -> Tuple[bool, str]:
        """Determina si un enlace apunta a un archivo descargable según las extensiones permitidas."""
        href_lower = href.lower()
        for ext in self.adapter.allowed_extensions:
            if f".{ext}" in href_lower:
                return True, ext
        
        if any(kw in text.lower() for kw in ["descargar", "boletín", "reporte", "informe"]):
            if ".pdf" in href_lower:
                return True, "pdf"
            if ".xlsx" in href_lower or ".xls" in href_lower:
                return True, "xlsx"
            if ".csv" in href_lower:
                return True, "csv"

        return False, ""

    def discover_from_seeds(self) -> List[DiscoveredCandidate]:
        """Recorre las URLs semillas del adaptador y extrae todos los candidatos a recursos."""
        candidates: List[DiscoveredCandidate] = []

        for seed_url in self.adapter.seeds:
            if seed_url in self.visited_urls:
                continue

            logger.info(f"Escaneando página semilla: {seed_url}")
            self.visited_urls.add(seed_url)

            success, status, html = self.fetcher.fetch_html(seed_url)
            if not success or not html:
                logger.error(f"No se pudo cargar la semilla {seed_url} (HTTP {status})")
                continue

            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a", href=True)

            for a_tag in links:
                href = a_tag["href"].strip()
                if not href or href.startswith("#") or href.startswith("javascript:"):
                    continue

                abs_url = urljoin(seed_url, href)

                if self.adapter.is_url_excluded(abs_url):
                    continue

                domain = urlparse(abs_url).netloc
                if domain and domain not in self.adapter.allowed_domains:
                    continue

                anchor_text = a_tag.get_text(strip=True)
                parent_tag = a_tag.find_parent(["p", "li", "tr", "td", "div"])
                context_text = parent_tag.get_text(strip=True) if parent_tag else anchor_text

                is_download, ext = self._is_download_link(href, anchor_text)
                dataset_id = self.adapter.classify_dataset(abs_url, anchor_text)

                if is_download and dataset_id:
                    candidate = DiscoveredCandidate(
                        url=abs_url,
                        url_origin=seed_url,
                        anchor_text=anchor_text or href.split("/")[-1],
                        context_text=context_text,
                        dataset_id=dataset_id,
                        file_type=ext
                    )
                    candidates.append(candidate)

        return candidates
