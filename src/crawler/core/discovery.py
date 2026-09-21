"""
Dataset-first discovery engine.

Combines controlled BFS/DFS crawling, optional passive discovery channels and
semantic scoring while keeping the public API used by the orchestrator stable.
"""

import logging
import os
import re
from collections import deque
from typing import List, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from crawler.core.fetcher import HttpFetcher
from crawler.core.search_dorker import SearchDorker
from crawler.core.smart_robots import discover_sitemap_urls
from crawler.core.subdomain_finder import find_subdomains
from crawler.core.wayback_engine import query_wayback_urls
from crawler.sources.base_adapter import BaseSourceAdapter

logger = logging.getLogger(__name__)


class DiscoveredCandidate:
    """Represents a downloadable resource found during discovery."""

    def __init__(
        self,
        url: str,
        url_origin: str,
        anchor_text: str,
        context_text: str,
        dataset_id: str,
        file_type: str,
        relevance_score: float = 0.0,
        depth: int = 0,
    ):
        self.url = url
        self.url_origin = url_origin
        self.anchor_text = anchor_text
        self.context_text = context_text
        self.dataset_id = dataset_id
        self.file_type = file_type
        self.relevance_score = relevance_score
        self.depth = depth


class DiscoveryEngine:
    """Crawls source seeds in a controlled way and extracts download candidates."""

    def __init__(self, fetcher: HttpFetcher, adapter: BaseSourceAdapter):
        self.fetcher = fetcher
        self.adapter = adapter
        self.visited_urls: Set[str] = set()
        crawl_cfg = self.adapter.config.get("crawl", {})
        self.max_depth = int(crawl_cfg.get("max_depth", 1))
        self.max_pages = int(crawl_cfg.get("max_pages", 100))
        self.strategy = str(crawl_cfg.get("strategy", "bfs")).lower()
        self.semantic_keywords = self._load_semantic_keywords()

    def _load_semantic_keywords(self) -> Set[str]:
        defaults = {
            "descargar",
            "descarga",
            "documento",
            "documentos",
            "archivo",
            "archivos",
            "boletin",
            "boletín",
            "reporte",
            "informe",
            "memoria",
            "memorias",
            "estadistica",
            "estadísticas",
            "estadística",
            "financiera",
            "financiero",
            "datos",
            "csv",
            "xlsx",
            "xls",
            "pdf",
            "zip",
            "mensual",
            "trimestral",
            "anual",
            "fiscal",
            "ifd",
            "instituciones",
            "financieras",
            "bursatil",
            "bursátil",
            "download",
            "downloads",
        }
        for rule in self.adapter.config.get("classification", {}).get("dataset_rules", []):
            for keyword in rule.get("title_keywords", []):
                defaults.update(str(keyword).lower().split())
        for token in self.adapter.config.get("classification", {}).get("document_path_tokens", []):
            defaults.add(str(token).lower().strip())
        return defaults

    @staticmethod
    def _normalize_visit_url(url: str) -> str:
        parsed = urlparse(url)
        query_pairs = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            key_l = key.lower()
            if key_l.startswith("utm_") or key_l in {"fbclid", "gclid", "x16877", "cache", "timestamp", "_"}:
                continue
            query_pairs.append((key, value))
        query = urlencode(sorted(query_pairs), doseq=True)
        return urlunparse(parsed._replace(query=query, fragment=""))

    def _is_allowed_domain(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            return False
        domain = parsed.netloc.lower()
        allowed = {d.lower() for d in self.adapter.allowed_domains}
        return not domain or not allowed or domain in allowed

    def _score_link(self, url: str, anchor_text: str, context_text: str, depth: int) -> float:
        combined = f"{url} {anchor_text} {context_text}".lower()
        score = 0.0

        score += sum(1.0 for kw in self.semantic_keywords if kw in combined)

        if any(f".{ext}" in url.lower() for ext in self.adapter.allowed_extensions):
            score += 5.0

        path_tokens = [
            "download",
            "downloads",
            "descarga",
            "descargar",
            "archivo",
            "archivos",
            "documento",
            "documentos",
            "reporte",
            "reportes",
            "informe",
            "informes",
            "boletin",
            "boletín",
            "estadistica",
            "estadística",
            "financiera",
            "financiero",
            "memoria",
            "memorias",
            "ifd",
        ]

        if any(token in url.lower() for token in path_tokens):
            score += 2.5
        if any(token in combined for token in path_tokens):
            score += 2.0
        if any(token in (anchor_text or "").lower() for token in path_tokens):
            score += 1.25
        if any(token in (context_text or "").lower() for token in path_tokens):
            score += 0.75

        if any(segment.isdigit() for segment in url.split("/")):
            score += 0.5

        if anchor_text:
            score += 0.75
        if context_text:
            score += 0.25

        score -= depth * 0.25
        return score

    def _extract_pagination_links(self, soup: BeautifulSoup, current_url: str) -> List[str]:
        """
        Extrae enlaces de paginación HTML en base a:
        1. <a rel="next"> o <link rel="next">
        2. Clases CSS comunes de paginación (.pagination, .pager, etc.)
        3. Enlaces con parámetros de consulta de página (?page=N, ?p=N, etc.)
        4. Enlaces con patrones de ruta (/page/N/, /p/N/)
        5. Texto de paginación ("Siguiente", "Next", ">", "»", o dígitos aislados)
        """
        pagination_links: List[str] = []
        seen: Set[str] = set()

        # 1. rel="next" en link o a
        for tag in soup.find_all(["a", "link"], rel=lambda r: r and "next" in str(r).lower()):
            href = tag.get("href")
            if href:
                full_url = urljoin(current_url, href.strip())
                norm = self._normalize_visit_url(full_url)
                if norm not in seen and self._is_allowed_domain(norm):
                    seen.add(norm)
                    pagination_links.append(norm)

        # 2. Análisis heurístico de etiquetas <a>
        page_param_regex = re.compile(r"[?&](page|p|pagina|paged|offset|start)=(\d+)", re.I)
        page_path_regex = re.compile(r"/(?:page|p|pagina)/(\d+)/?", re.I)
        next_text_regex = re.compile(r"^(siguiente|next|>|»|›|página\s*\d+|\d+)$", re.I)

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith("#") or href.lower().startswith(
                ("javascript:", "mailto:", "tel:")
            ):
                continue

            full_url = urljoin(current_url, href)
            norm = self._normalize_visit_url(full_url)
            if norm in seen or not self._is_allowed_domain(norm):
                continue

            # Descartar si es enlace directo de archivo descargable por extensión
            parsed_path = urlparse(href).path
            _, file_ext = os.path.splitext(parsed_path)
            allowed_clean = {e.lower().lstrip('.') for e in (getattr(self.adapter, "allowed_extensions", []) or [])}
            ext_clean = file_ext.lower().lstrip('.')
            if ext_clean in allowed_clean or any(f".{ext}" in href.lower() for ext in allowed_clean):
                continue

            text = a_tag.get_text(strip=True).lower()
            classes = " ".join(a_tag.get("class", [])).lower()
            parent_classes = " ".join(a_tag.parent.get("class", [])).lower() if a_tag.parent else ""

            is_pagination = False

            # Heurística A: Patrón en query o path
            if page_param_regex.search(norm) or page_path_regex.search(norm):
                is_pagination = True
            # Heurística B: Clases CSS de paginación
            elif any(c in classes or c in parent_classes for c in ["pagination", "pager", "nav-links", "page-numbers"]):
                is_pagination = True
            # Heurística C: Texto típico de paginador
            elif next_text_regex.match(text):
                is_pagination = True

            if is_pagination:
                seen.add(norm)
                pagination_links.append(norm)

        return pagination_links

    def _is_download_link(self, href: str, text: str) -> Tuple[bool, str]:
        href_lower = href.lower()
        text_lower = text.lower()
        allowed_clean = {e.lower().lstrip('.') for e in (getattr(self.adapter, "allowed_extensions", []) or [])}

        parsed_path = urlparse(href).path
        _, file_ext = os.path.splitext(parsed_path)
        ext_clean = file_ext.lower().lstrip('.')

        # Si la URL tiene una extensión explícita en su ruta:
        if ext_clean:
            if ext_clean in allowed_clean:
                return True, ext_clean
            # Si no es un script dinámico ejecutable (que pueda devolver un doc por query params),
            # es un archivo estático no permitido (ej. .sha, .html, .jpg, .png, .txt) -> descartar
            dynamic_scripts = {"php", "aspx", "asp", "jsp", "ashx", "do", "action"}
            if ext_clean not in dynamic_scripts:
                return False, ""

        # Si no tiene extensión en la ruta o es script dinámico, buscar allowed_extensions en query o href
        for ext in allowed_clean:
            if f".{ext}" in href_lower:
                return True, ext

        path_tokens = [
            "/download",
            "/downloads",
            "/descarga",
            "/descargar",
            "/archivo",
            "/archivos",
            "/documento",
            "/documentos",
            "/reporte",
            "/reportes",
            "/informe",
            "/informes",
            "/boletin",
            "/boletín",
            "/estadistica",
            "/estadística",
            "/financiera",
            "/ifd",
        ]

        if any(token in href_lower for token in path_tokens):
            return True, "document"

        text_tokens = [
            "descargar",
            "descarga",
            "boletín",
            "boletin",
            "reporte",
            "informe",
            "archivo",
            "archivos",
            "documento",
            "documentos",
            "estadistica",
            "estadística",
            "financiera",
            "memoria",
        ]

        if any(kw in text_lower for kw in text_tokens) and any(kw in href_lower for kw in ["reporte", "informe", "archivo", "boletin", "boletín", "estadistica", "financiera", "download", "descarga", "documentos", "ifd"]):
            return True, "document"

        return False, ""

    def _add_passive_candidates(self, candidates: List[DiscoveredCandidate]) -> None:
        if bool(self.adapter.config.get("crawl", {}).get("use_wayback", False)):
            domains = self.adapter.allowed_domains or [urlparse(self.adapter.base_url).netloc]
            for domain in domains:
                for url in query_wayback_urls(domain, file_types=self.adapter.allowed_extensions, limit=500):
                    dataset_id = self.adapter.classify_dataset(url, "")
                    if not dataset_id:
                        continue
                    file_type = url.rsplit(".", 1)[-1].lower() if "." in url else ""
                    candidates.append(
                        DiscoveredCandidate(
                            url=url,
                            url_origin="wayback",
                            anchor_text=url.split("/")[-1],
                            context_text="",
                            dataset_id=dataset_id,
                            file_type=file_type,
                            relevance_score=self._score_link(url, url, "", 0),
                        )
                    )

        if bool(self.adapter.config.get("crawl", {}).get("use_search_dorking", False)):
            dorker = SearchDorker.from_config(self.adapter.config)
            domain = urlparse(self.adapter.base_url).netloc or self.adapter.base_url
            for url in dorker.search_domain_documents(domain, self.adapter.allowed_extensions):
                dataset_id = self.adapter.classify_dataset(url, "")
                if not dataset_id:
                    continue
                file_type = url.rsplit(".", 1)[-1].lower() if "." in url else ""
                candidates.append(
                    DiscoveredCandidate(
                        url=url,
                        url_origin="search_dorking",
                        anchor_text=url.split("/")[-1],
                        context_text="",
                        dataset_id=dataset_id,
                        file_type=file_type,
                        relevance_score=self._score_link(url, url, "", 0),
                    )
                )

    def _add_api_candidates(self, candidates: List[DiscoveredCandidate]) -> None:
        crawl_cfg = getattr(self.adapter, "config", {}).get("crawl", {}) if hasattr(self.adapter, "config") else {}
        api_endpoints = crawl_cfg.get("api_endpoints") or getattr(self.adapter, "api_endpoints", [])
        if not api_endpoints:
            return

        from crawler.core.api_consumer import ApiConsumer

        consumer = ApiConsumer(
            base_url=self.adapter.base_url,
            allowed_domains=self.adapter.allowed_domains,
            allowed_extensions=self.adapter.allowed_extensions,
            is_url_excluded_cb=self.adapter.is_url_excluded,
            rate_limit_per_second=getattr(self.adapter, "rate_limit_per_second", 1.0),
        )

        api_candidates = consumer.discover_from_endpoints(api_endpoints)
        for cand in api_candidates:
            dataset_id = self.adapter.classify_dataset(cand.url, cand.anchor_text)
            cand.dataset_id = dataset_id
            candidates.append(cand)

    def _build_seed_list(self) -> List[str]:
        crawl_seeds = list(dict.fromkeys(self.adapter.seeds))
        crawl_cfg = self.adapter.config.get("crawl", {})

        if bool(crawl_cfg.get("use_subdomain_enumeration", False)):
            scheme = urlparse(self.adapter.base_url).scheme or "https"
            for domain in self.adapter.allowed_domains:
                for subdomain in find_subdomains(domain):
                    seed_candidate = f"{scheme}://{subdomain}/"
                    if seed_candidate not in crawl_seeds:
                        logger.info("Adding seed from certificate transparency: %s", seed_candidate)
                        crawl_seeds.append(seed_candidate)

        if bool(crawl_cfg.get("use_sitemaps", True)):
            checked_bases = set()
            for seed_url in list(crawl_seeds):
                parsed = urlparse(seed_url)
                if not parsed.scheme or not parsed.netloc:
                    continue
                base = f"{parsed.scheme}://{parsed.netloc}"
                if base in checked_bases:
                    continue
                checked_bases.add(base)
                for sitemap_url in discover_sitemap_urls(base, self.fetcher):
                    if sitemap_url not in crawl_seeds and self._is_allowed_domain(sitemap_url):
                        crawl_seeds.append(sitemap_url)

        return crawl_seeds

    def discover_from_seeds(self) -> List[DiscoveredCandidate]:
        candidates: List[DiscoveredCandidate] = []
        self._add_passive_candidates(candidates)
        self._add_api_candidates(candidates)
        seen_candidate_urls: Set[str] = {c.url for c in candidates}

        seed_list = self._build_seed_list()
        queue = deque((seed, 0) for seed in seed_list)
        enqueued_urls: Set[str] = {self._normalize_visit_url(seed) for seed in seed_list}
        pages_scanned = 0

        while queue and pages_scanned < self.max_pages:
            page_url, depth = queue.popleft() if self.strategy != "dfs" else queue.pop()
            visit_url = self._normalize_visit_url(page_url)
            if visit_url in self.visited_urls:
                continue
            if self.adapter.is_url_excluded(page_url) or not self._is_allowed_domain(page_url):
                continue

            logger.info("Scanning page: %s", page_url)
            self.visited_urls.add(visit_url)
            pages_scanned += 1

            # Si la URL en la cola es directamente un documento, registrarla como candidato y no parsear como HTML
            url_clean = page_url.split("?")[0].split("#")[0].lower()
            if any(url_clean.endswith(f".{ext}") for ext in self.adapter.allowed_extensions):
                dataset_id = self.adapter.classify_dataset(page_url, "")
                if dataset_id and page_url not in seen_candidate_urls:
                    seen_candidate_urls.add(page_url)
                    file_type = url_clean.rsplit(".", 1)[-1] if "." in url_clean else ""
                    candidates.append(
                        DiscoveredCandidate(
                            url=page_url,
                            url_origin="seed" if depth == 0 else "link",
                            anchor_text=page_url.split("/")[-1].split("?")[0],
                            context_text="",
                            dataset_id=dataset_id,
                            file_type=file_type,
                            relevance_score=10.0,
                        )
                    )
                continue

            success, status, html = self.fetcher.fetch_html(page_url)
            if not success or not html:
                logger.error("Could not load %s (HTTP %s)", page_url, status)
                continue

            try:
                soup = BeautifulSoup(html, "html.parser")
            except Exception as e:
                logger.warning("No se pudo parsear HTML de %s: %s", page_url, e)
                continue
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                href_lower = href.lower()
                if not href or href.startswith("#") or href_lower.startswith(
                    ("javascript:", "mailto:", "tel:", "fax:", "whatsapp:", "sms:")
                ):
                    continue

                abs_url = self._normalize_visit_url(urljoin(page_url, href))
                if self.adapter.is_url_excluded(abs_url) or not self._is_allowed_domain(abs_url):
                    continue

                anchor_text = a_tag.get_text(strip=True)
                parent_tag = a_tag.find_parent(["p", "li", "tr", "td", "div", "section", "article"])
                context_text = parent_tag.get_text(" ", strip=True) if parent_tag else anchor_text
                score = self._score_link(abs_url, anchor_text, context_text, depth)
                is_download, ext = self._is_download_link(href, anchor_text)
                dataset_id = self.adapter.classify_dataset(abs_url, anchor_text)

                if is_download and dataset_id:
                    # Deduplicación intra-corrida: evitar candidatos duplicados (O-31 / E-17)
                    if abs_url not in seen_candidate_urls:
                        seen_candidate_urls.add(abs_url)
                        candidates.append(
                            DiscoveredCandidate(
                                url=abs_url,
                                url_origin=page_url,
                                anchor_text=anchor_text or href.split("/")[-1],
                                context_text=context_text,
                                dataset_id=dataset_id,
                                file_type=ext,
                                relevance_score=score,
                                depth=depth,
                            )
                        )
                elif depth < self.max_depth and score >= 0:
                    next_visit = self._normalize_visit_url(abs_url)
                    if next_visit not in self.visited_urls and next_visit not in enqueued_urls:
                        enqueued_urls.add(next_visit)
                        queue.append((next_visit, depth + 1))

            # Encolar enlaces de paginación descubiertos en la página
            pagination_links = self._extract_pagination_links(soup, page_url)
            for p_url in pagination_links:
                if p_url not in self.visited_urls and p_url not in enqueued_urls:
                    enqueued_urls.add(p_url)
                    # Paginación preserva el depth actual (mismo nivel temático)
                    queue.append((p_url, depth))

        candidates.sort(key=lambda item: item.relevance_score, reverse=True)
        return candidates
