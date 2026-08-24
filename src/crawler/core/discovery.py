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
from crawler.core.wayback_engine import query_wayback_urls
from crawler.core.subdomain_finder import find_subdomains

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

        # Optional: enrich seeds with Wayback CDX discoveries if adapter config enables it
        use_wayback = False
        try:
            use_wayback = bool(self.adapter.config.get("crawl", {}).get("use_wayback", False))
        except Exception:
            use_wayback = False

        if use_wayback:
            # Query Wayback for the base domain(s) and add discovered file URLs as candidates
            domains = self.adapter.allowed_domains or [self.adapter.base_url]
            for dom in domains:
                wb_urls = query_wayback_urls(dom, file_types=self.adapter.allowed_extensions, limit=500)
                for url in wb_urls:
                    if url in self.visited_urls:
                        continue
                    self.visited_urls.add(url)
                    dataset_id = self.adapter.classify_dataset(url, "")
                    # derive file type from extension
                    file_type = ""
                    if "." in url:
                        file_type = url.rsplit(".", 1)[1].lower()
                    candidate = DiscoveredCandidate(
                        url=url,
                        url_origin="wayback",
                        anchor_text=url.split("/")[-1],
                        context_text="",
                        dataset_id=dataset_id,
                        file_type=file_type
                    )
                    candidates.append(candidate)

        # Optional: expand seeds with discovered subdomains via Certificate Transparency (crt.sh)
        use_subdomains = False
        try:
            use_subdomains = bool(self.adapter.config.get("crawl", {}).get("use_subdomain_enumeration", False))
        except Exception:
            use_subdomains = False

        if use_subdomains:
            # derive scheme from base_url
            try:
                parsed = urlparse(self.adapter.base_url)
                scheme = parsed.scheme or "https"
            except Exception:
                scheme = "https"

            for dom in (self.adapter.allowed_domains or []):
                subs = find_subdomains(dom)
                for sub in subs:
                    seed_candidate = f"{scheme}://{sub}/"
                    if seed_candidate not in self.adapter.seeds and seed_candidate not in self.visited_urls:
                        logger.info(f"Añadiendo seed desde subdominio descubierto: {seed_candidate}")
                        # prepend to seeds list to scan them as well
                        candidates.append(DiscoveredCandidate(
                            url=seed_candidate,
                            url_origin="subdomain_discovery",
                            anchor_text=sub,
                            context_text="",
                            dataset_id="",
                            file_type=""
                        ))

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
