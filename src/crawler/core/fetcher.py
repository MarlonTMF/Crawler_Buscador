"""
Cliente HTTP resiliente y respetuoso de buenas prácticas de web scraping para el prospector externo.
Soporta:
- Verificación automática y estricta de rules en robots.txt (urllib.robotparser).
- Control de frecuencia per-domain (Rate-limiting).
- Reintentos exponenciales y backoff para respuestas 429 (Too Many Requests) y 5xx.
- Identificación profesional con User-Agent personalizado.
- Solicitudes HTTP HEAD para minimizar consumo de ancho de banda del servidor.
- Solicitudes HTTP GET binarias para descarga de comprimidos y archivos.
"""

import os
import time
import logging
import re
from typing import Optional, Dict, Any, Tuple, List
import json
import urllib.parse
from datetime import datetime
from pathlib import Path


def _load_gemini_key_from_env_file() -> Optional[str]:
    """Carga GEMINI_API_KEY desde .env del proyecto o del entorno del sistema."""
    if os.getenv("GEMINI_API_KEY"):
        return os.getenv("GEMINI_API_KEY")

    candidate_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[3] / ".env",
        Path.home() / ".env",
    ]

    seen = set()
    for env_path in candidate_paths:
        path = env_path.resolve() if env_path.exists() else env_path
        if str(path) in seen:
            continue
        seen.add(str(path))
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = [part.strip() for part in stripped.split("=", 1)]
                if key == "GEMINI_API_KEY":
                    return value.strip("\"'")
        except Exception:
            continue
    return None
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import requests
from requests import exceptions as requests_exceptions

from crawler.core.headless_fetcher import HeadlessFetcher

logger = logging.getLogger(__name__)


class HttpFetcher:
    """Cliente HTTP ético y resiliente con verificación de robots.txt y rate-limiting."""

    def __init__(
        self,
        user_agent: str = "ProspectorExterno/1.0 (+contacto-proyecto-datax)",
        timeout: int = 15,
        max_retries: int = 3,
        rate_limit_seconds: float = 1.0,
        honor_robots_txt: bool = True,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-3.6-flash",
        use_playwright: bool = False,
        headless_fetcher: Optional[HeadlessFetcher] = None,
        auto_headless_on_403: bool = True,
        verify_ssl: bool = True,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit_seconds = rate_limit_seconds
        self.honor_robots_txt = honor_robots_txt
        self.gemini_api_key = gemini_api_key or _load_gemini_key_from_env_file()
        self.gemini_model = gemini_model
        self.use_playwright = use_playwright
        self.headless_fetcher = headless_fetcher
        self.auto_headless_on_403 = auto_headless_on_403
        self.verify_ssl = verify_ssl
        
        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        if not self.verify_ssl:
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass
        self.session.headers.update({"User-Agent": self.user_agent})
        
        self._last_request_time: Dict[str, float] = {}
        self._robots_parsers: Dict[str, RobotFileParser] = {}
        self.resolved_via_headless_urls: Set[str] = set()
        self.last_fetch_resolved_via_headless: bool = False

    def is_resolved_via_headless(self, url: str) -> bool:
        """Indica si una URL fue resuelta exitosamente mediante reintento headless ante 403."""
        return url in self.resolved_via_headless_urls

    def _fetch_html_via_headless(self, url: str) -> Tuple[bool, int, Optional[str]]:
        """Reintenta la obtención de HTML usando HeadlessFetcher (Playwright) ante bloqueos WAF/403."""
        if self.headless_fetcher is None:
            # Mantener 30s por defecto para challenges de Cloudflare que requieren tiempo de resolución
            self.headless_fetcher = HeadlessFetcher(timeout_ms=max(30000, self.timeout * 1000))
        try:
            ok, status, result = self.headless_fetcher.fetch(url)
            if ok and result is not None and result.html:
                return True, status or 200, result.html
            return False, status or 0, None
        except Exception as exc:
            logger.warning("Error durante reintento headless para %s: %s", url, exc)
            return False, 0, None

    def _get_robots_parser(self, domain: str, base_url: str) -> Optional[RobotFileParser]:
        """Carga y parsea el archivo robots.txt del dominio objetivo."""
        if domain in self._robots_parsers:
            return self._robots_parsers[domain]

        robots_url = urljoin(f"{urlparse(base_url).scheme}://{domain}", "/robots.txt")
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            logger.info(f"Verificando robots.txt en: {robots_url}")
            extra_kwargs = {} if self.verify_ssl else {"verify": False}
            response = self.session.get(robots_url, timeout=10, **extra_kwargs)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
                logger.info(f"robots.txt cargado exitosamente para [{domain}]")
            else:
                logger.warning(f"No se pudo cargar robots.txt de [{domain}] (HTTP {response.status_code}), permitiendo crawl con cautela.")
                parser.allow_all = True
        except Exception as e:
            logger.warning(f"Error al obtener robots.txt de [{domain}]: {e}")
            parser.allow_all = True

        self._robots_parsers[domain] = parser
        return parser

    def is_url_allowed_by_robots(self, url: str) -> bool:
        """Verifica si la URL está autorizada por robots.txt."""
        if not self.honor_robots_txt:
            return True

        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return True

        parser = self._get_robots_parser(domain, url)
        if parser:
            allowed = parser.can_fetch(self.user_agent, url) or parser.can_fetch("*", url)
            if not allowed:
                logger.warning(f"URL denegada por robots.txt: {url}")
            return allowed

        return True

    def _apply_rate_limit(self, url: str) -> None:
        """Aplica una pausa respetuosa entre solicitudes para no sobrecargar el servidor."""
        domain = urlparse(url).netloc
        now = time.time()
        if domain in self._last_request_time:
            elapsed = now - self._last_request_time[domain]
            if elapsed < self.rate_limit_seconds:
                sleep_time = self.rate_limit_seconds - elapsed
                time.sleep(sleep_time)
        self._last_request_time[domain] = time.time()

    @staticmethod
    def _classify_request_error(exc: Exception) -> str:
        text = str(exc).lower()
        if isinstance(exc, requests_exceptions.SSLError):
            return "SSL_ERROR"
        if isinstance(exc, requests_exceptions.Timeout):
            return "TIMEOUT"
        if "dns" in text or "name or service not known" in text or "temporary failure in name resolution" in text:
            return "DNS_ERROR"
        if "ssl" in text or "certificate" in text:
            return "SSL_ERROR"
        if "timed out" in text or "timeout" in text:
            return "TIMEOUT"
        return "CONN_ERROR"

    @staticmethod
    def _extract_document_counts(html: Optional[str], url: str, network_urls: Optional[list[str]] = None) -> Tuple[bool, float, int, list[str]]:
        if not html:
            return False, 0.0, 0, []

        candidate_text = f"{html} {url}"
        lowered = candidate_text.lower()
        strong_tokens = [
            ".pdf", ".xlsx", ".xls", ".csv", ".zip",
            "/download", "/downloads", "/descarga", "/descargar",
            "descargar", "descarga", "documento", "documentos",
            "reporte", "reportes", "informe", "informes",
            "archivo", "archivos", "boletin", "boletín",
            "estadistica", "estadísticas", "memoria", "memorias", "ifd"
        ]
        weak_tokens = ["financiera", "financiero", "institucion", "institución"]

        url_matches = set()
        for match in re.findall(r'href=["\']([^"\']+)["\']|src=["\']([^"\']+)["\']', html, re.IGNORECASE):
            for item in match:
                if item:
                    url_matches.add(item)
        for item in network_urls or []:
            url_matches.add(str(item))

        doc_links = 0
        for link in url_matches:
            lower_link = link.lower()
            if any(ext in lower_link for ext in [".pdf", ".xlsx", ".xls", ".csv", ".zip"]) or any(token in lower_link for token in ["/download", "/downloads", "/descarga", "/descargar", "reporte", "informe", "archivo", "documento"]):
                doc_links += 1

        keyword_hits: list[str] = []
        for token in [
            "reporte", "informe", "financiero", "estadistica", "documento", "archivo",
            "desarrollo", "activo", "mensual", "anual", "trimestral"
        ]:
            if token in lowered and token not in keyword_hits:
                keyword_hits.append(token)

        has_strong_signal = any(token in lowered for token in strong_tokens) or doc_links > 0 or bool(keyword_hits)
        has_weak_signal = any(token in lowered for token in weak_tokens)

        if has_strong_signal and not (has_weak_signal and not any(token in lowered for token in ["reporte", "reportes", "informe", "informes", "descargar", "documento", "documentos", "archivo", "archivos"])):
            return True, 3.0, doc_links, keyword_hits

        return bool(has_strong_signal), 3.0 if has_strong_signal else 2.0, doc_links, keyword_hits

    @staticmethod
    def _extract_document_samples(html_content: Optional[str], base_url: str) -> Dict[str, Any]:
        """Extrae muestras de enlaces documentales (PDF, XLSX, CSV) y un fragmento de texto limpio de la página."""
        if not html_content:
            return {"samples": [], "snippet_text": "", "file_type": None}
        
        import html as html_lib
        decoded_html = html_lib.unescape(html_content)

        # 1. Clean HTML to readable text snippet
        text_clean = re.sub(r'<script.*?>.*?</script>', ' ', decoded_html, flags=re.DOTALL | re.IGNORECASE)
        text_clean = re.sub(r'<style.*?>.*?</style>', ' ', text_clean, flags=re.DOTALL | re.IGNORECASE)
        text_clean = re.sub(r'<[^>]+>', ' ', text_clean)
        text_clean = ' '.join(text_clean.split())
        
        sentences = re.split(r'[.\n]', text_clean)
        matching_sentences = []
        for s in sentences:
            s_strip = s.strip()
            if len(s_strip) > 20 and any(kw in s_strip.lower() for kw in ["informe", "reporte", "estadistica", "memoria", "anual", "financier", "documento", "boletin"]):
                matching_sentences.append(s_strip)
                if len(' '.join(matching_sentences)) > 300:
                    break
        
        snippet = ' ... '.join(matching_sentences[:3]) if matching_sentences else text_clean[:250]
        
        # 2. Extract anchor links to documents
        samples = []
        seen = set()
        pattern = r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
        for match in re.finditer(pattern, decoded_html, re.IGNORECASE | re.DOTALL):
            href, anchor_text = match.groups()
            anchor_clean = re.sub(r'<[^>]+>', '', anchor_text).strip()
            lower_href = href.lower()
            
            file_type = None
            if '.pdf' in lower_href:
                file_type = 'PDF'
            elif '.xlsx' in lower_href or '.xls' in lower_href:
                file_type = 'XLSX'
            elif '.csv' in lower_href:
                file_type = 'CSV'
            elif '.doc' in lower_href or '.docx' in lower_href:
                file_type = 'DOCX'
            elif '.zip' in lower_href:
                file_type = 'ZIP'
            elif any(kw in lower_href for kw in ['/download', '/descarga', 'reporte', 'informe', 'documento']):
                file_type = 'DOC'
                
            if file_type:
                try:
                    full_url = urllib.parse.urljoin(base_url, href)
                except Exception:
                    full_url = href
                if full_url not in seen and full_url.startswith('http'):
                    seen.add(full_url)
                    title = anchor_clean if (anchor_clean and len(anchor_clean) > 2) else full_url.split('/')[-1]
                    samples.append({
                        "title": title[:70],
                        "url": full_url,
                        "file_type": file_type
                    })
                    if len(samples) >= 10:
                        break
                        
        return {
            "samples": samples,
            "snippet_text": snippet[:350],
            "file_type": samples[0]["file_type"] if samples else ("HTML" if snippet else None)
        }

    @staticmethod
    def _detect_document_signal(html: Optional[str], url: str, network_urls: Optional[list[str]] = None) -> Tuple[bool, float]:
        has_signal, score, _, _ = HttpFetcher._extract_document_counts(html, url, network_urls)
        return has_signal, score

    def validate_url_access(
        self,
        url: str,
        browser_fallback: bool = False,
        headless_fetcher: Optional[Any] = None,
        force_browser_html: Optional[str] = None,
        allow_variants: bool = True,
    ) -> Dict[str, Any]:
        """Validate whether a URL is actually reachable and return an operational score cap."""
        if not self.is_url_allowed_by_robots(url):
            return {
                "url": url,
                "reachable_http": False,
                "status_code": 403,
                "error_type": "ROBOTS_BLOCKED",
                "effective_score": 2.0,
                "has_document_signal": False,
            }

        html_candidates: list[str] = []
        browser_html: Optional[str] = force_browser_html

        use_headless = browser_fallback or self.use_playwright
        if use_headless and headless_fetcher is None:
            headless_fetcher = self.headless_fetcher or HeadlessFetcher()

        try:
            ok, status, headers = self.fetch_head(url)
            if ok:
                html_candidates.append(("http", status, ""))
                page_html = self._last_http_text(url)
                has_document_signal, effective_score, doc_links, keyword_hits = self._extract_document_counts(page_html, url)
                doc_details = self._extract_document_samples(page_html, url)
                return {
                    "url": url,
                    "reachable_http": True,
                    "status_code": status,
                    "final_url": url,
                    "error_type": None,
                    "effective_score": effective_score,
                    "has_document_signal": has_document_signal,
                    "document_links_found": doc_links,
                    "keyword_hits": keyword_hits,
                    "document_evidence": {
                        "keyword_hits": keyword_hits,
                        "file_type": doc_details.get("file_type"),
                        "quality_score": effective_score,
                        "snippet_text": doc_details.get("snippet_text") or "",
                        "samples": doc_details.get("samples") or [],
                    },
                }
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("HEAD validation raised unexpected error for %s: %s", url, exc)

        try:
            ok, status, text = self.fetch_html(url)
            if ok and text is not None:
                has_document_signal, effective_score, doc_links, keyword_hits = self._extract_document_counts(text, url)
                doc_details = self._extract_document_samples(text, url)
                res_access = {
                    "url": url,
                    "reachable_http": True,
                    "status_code": status,
                    "final_url": url,
                    "error_type": None,
                    "effective_score": effective_score,
                    "has_document_signal": has_document_signal,
                    "document_links_found": doc_links,
                    "keyword_hits": keyword_hits,
                    "document_evidence": {
                        "keyword_hits": keyword_hits,
                        "file_type": doc_details.get("file_type"),
                        "quality_score": effective_score,
                        "snippet_text": doc_details.get("snippet_text") or "",
                        "samples": doc_details.get("samples") or [],
                    },
                }
                if self.last_fetch_resolved_via_headless:
                    res_access["browser_fallback_used"] = True
                    res_access["resolved_via_headless"] = True
                    logger.info("Auditoría: URL %s validada exitosamente vía headless tras bloqueo 403", url)
                return res_access
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("GET validation raised unexpected error for %s: %s", url, exc)

        if force_browser_html is not None:
            has_document_signal, effective_score, doc_links, keyword_hits = self._extract_document_counts(force_browser_html, url)
            doc_details = self._extract_document_samples(force_browser_html, url)
            return {
                "url": url,
                "reachable_http": False,
                "status_code": 0,
                "final_url": url,
                "error_type": "CONN_ERROR",
                "effective_score": effective_score,
                "has_document_signal": has_document_signal,
                "document_links_found": doc_links,
                "keyword_hits": keyword_hits,
                "browser_fallback_used": True,
                "document_evidence": {
                    "keyword_hits": keyword_hits,
                    "file_type": doc_details.get("file_type"),
                    "quality_score": effective_score,
                    "snippet_text": doc_details.get("snippet_text") or "",
                    "samples": doc_details.get("samples") or [],
                },
            }

        if use_headless and headless_fetcher is not None:
            try:
                ok, status, result = headless_fetcher.fetch(url)
                if ok and result is not None:
                    browser_html = result.html
                    has_document_signal, effective_score, doc_links, keyword_hits = self._extract_document_counts(browser_html, url, getattr(result, "network_urls", None))
                    doc_details = self._extract_document_samples(browser_html, url)
                    return {
                        "url": url,
                        "reachable_http": True,
                        "status_code": status,
                        "final_url": url,
                        "error_type": None,
                        "effective_score": effective_score,
                        "has_document_signal": has_document_signal,
                        "document_links_found": doc_links,
                        "keyword_hits": keyword_hits,
                        "document_evidence": {
                            "keyword_hits": keyword_hits,
                            "file_type": doc_details.get("file_type"),
                            "quality_score": effective_score,
                            "snippet_text": doc_details.get("snippet_text") or "",
                            "samples": doc_details.get("samples") or [],
                        },
                        "browser_fallback_used": True,
                    }
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning("Browser fallback failed for %s: %s", url, exc)

        # Before returning a hard CONN_ERROR, try simple URL-variant fallbacks
        if allow_variants:
            try:
                candidate = self._try_url_variants(url)
                if candidate:
                    logger.info("URL %s likely moved -> trying candidate %s", url, candidate)
                    self._record_moved_url(original=url, resolved=candidate)
                    candidate_result = self.validate_url_access(
                        candidate,
                        browser_fallback=browser_fallback,
                        headless_fetcher=headless_fetcher,
                        force_browser_html=force_browser_html,
                        allow_variants=False,
                    )
                    candidate_result["mapped_from"] = url
                    candidate_result["resolved_from_variant"] = True
                    candidate_result["original_url"] = url
                    if candidate_result.get("final_url") == candidate:
                        candidate_result["variant_source"] = "gemini" if any(
                            item.get("url") == candidate and item.get("source") == "gemini"
                            for item in self._probe_gemini_alternatives(url)
                        ) else "variant"
                    return candidate_result
            except Exception as e:
                logger.warning("Variant fallback failed for %s: %s", url, e)

        return {
            "url": url,
            "reachable_http": False,
            "status_code": 0,
            "final_url": url,
            "error_type": "CONN_ERROR",
            "effective_score": 2.0,
            "has_document_signal": False,
            "document_links_found": 0,
            "keyword_hits": [],
            "gemini_candidates": self._ask_gemini_for_alternatives(url),
        }

    def _last_http_text(self, url: str) -> Optional[str]:
        try:
            _, _, text = self.fetch_html(url)
            return text
        except Exception:
            return None

    def fetch_head(self, url: str) -> Tuple[bool, int, Dict[str, str]]:
        """Realiza solicitud HEAD para metadatos respetando robots.txt y rate limits."""
        if not self.is_url_allowed_by_robots(url):
            return False, 403, {}

        self._apply_rate_limit(url)
        for attempt in range(1, self.max_retries + 1):
            try:
                head_timeout = min(float(self.timeout), 5.0)
                extra_kwargs = {} if self.verify_ssl else {"verify": False}
                response = self.session.head(
                    url, timeout=(3.0, head_timeout), allow_redirects=True, **extra_kwargs
                )
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5 * attempt))
                    logger.warning(f"Rate limit 429 recibido en HEAD {url}. Esperando {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                if response.status_code == 405:
                    logger.info("HEAD no permitido en %s; fallback a GET.", url)
                    return False, 405, dict(response.headers)

                return (response.status_code == 200), response.status_code, dict(response.headers)
            except requests_exceptions.RequestException as e:
                error_name = self._classify_request_error(e)
                logger.warning(f"HEAD {url} intento {attempt}/{self.max_retries} falló: {error_name} ({e})")
                if attempt == self.max_retries:
                    return False, 0, {}
                time.sleep(1.5 * attempt)

        return False, 0, {}

    def fetch_html(self, url: str) -> Tuple[bool, int, Optional[str]]:
        """Descarga página HTML respetando robots.txt, rate limits y reintentos con backoff.
        Ante respuestas HTTP 403 (WAF/Cloudflare), dispara un reintento condicional con navegador real.
        """
        self.last_fetch_resolved_via_headless = False
        if not self.is_url_allowed_by_robots(url):
            return False, 403, None

        if self.use_playwright:
            self._apply_rate_limit(url)
            if self.headless_fetcher is None:
                self.headless_fetcher = HeadlessFetcher(timeout_ms=self.timeout * 1000)
            ok, status, result = self.headless_fetcher.fetch(url)
            if ok and result is not None:
                return True, status, result.html
            return False, status, None

        self._apply_rate_limit(url)
        for attempt in range(1, self.max_retries + 1):
            try:
                extra_kwargs = {} if self.verify_ssl else {"verify": False}
                response = self.session.get(url, timeout=self.timeout, **extra_kwargs)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5 * attempt))
                    logger.warning(f"Rate limit 429 recibido en GET {url}. Esperando {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                response.encoding = response.apparent_encoding or "utf-8"
                if response.status_code == 200:
                    return True, 200, response.text

                # Reintento automático condicional con Headless ante 403 (D-03)
                if response.status_code == 403 and self.auto_headless_on_403:
                    logger.warning(
                        "GET HTML %s respondió 403 Forbidden con HTTP simple. Disparando reintento automático condicional con HeadlessFetcher...",
                        url,
                    )
                    h_ok, h_status, h_html = self._fetch_html_via_headless(url)
                    if h_ok and h_html:
                        logger.info(
                            "URL %s respondió 403 en HTTP simple -> resuelta exitosamente vía headless (status %s)",
                            url,
                            h_status,
                        )
                        self.resolved_via_headless_urls.add(url)
                        self.last_fetch_resolved_via_headless = True
                        return True, h_status, h_html
                    else:
                        logger.warning(
                            "Reintento headless para %s ante 403 no tuvo éxito o devolvió contenido vacío (status %s)",
                            url,
                            h_status,
                        )
                        return False, response.status_code, None

                return False, response.status_code, None
            except requests_exceptions.RequestException as e:
                error_name = self._classify_request_error(e)
                logger.warning(f"GET HTML {url} intento {attempt}/{self.max_retries} falló: {error_name} ({e})")
                if attempt == self.max_retries:
                    return False, 0, None
                time.sleep(1.5 * attempt)

        return False, 0, None

    def fetch_bytes(self, url: str) -> Tuple[bool, int, Optional[bytes]]:
        """Descarga el contenido binario de una URL (ej. para descomprimir en memoria)."""
        if not self.is_url_allowed_by_robots(url):
            return False, 403, None

        self._apply_rate_limit(url)
        for attempt in range(1, self.max_retries + 1):
            try:
                bytes_timeout = min(float(self.timeout), 10.0)
                extra_kwargs = {} if self.verify_ssl else {"verify": False}
                response = self.session.get(url, timeout=(4.0, bytes_timeout), **extra_kwargs)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5 * attempt))
                    logger.warning(f"Rate limit 429 recibido en GET bytes {url}. Esperando {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                if response.status_code == 200:
                    return True, 200, response.content
                return False, response.status_code, None
            except requests_exceptions.RequestException as e:
                error_name = self._classify_request_error(e)
                logger.warning(f"GET bytes {url} intento {attempt}/{self.max_retries} falló: {error_name} ({e})")
                if attempt == self.max_retries:
                    return False, 0, None
                time.sleep(1.5 * attempt)

        return False, 0, None

    @staticmethod
    def _normalize_candidate_url(raw_url: str) -> Optional[str]:
        if not raw_url:
            return None
        candidate = raw_url.strip()
        if not candidate:
            return None
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        if not parsed.netloc:
            return None
        return candidate.rstrip() if candidate.startswith(("http://", "https://")) else None

    def _ask_gemini_for_alternatives(self, url: str, failed_candidates: Optional[List[str]] = None) -> List[str]:
        """Query Gemini for candidate alternative URLs when local heuristics fail."""
    def _generate_gemini_content(self, prompt: str) -> str:
        """Invoca la API de Gemini probando en orden los modelos vigentes."""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY no configurada.")
        
        # Los nombres de modelo caducan seguido: gemini-2.0-flash y gemini-1.5-* se
        # retiraron el 2026-09-11, y gemini-2.5-flash dejó de estar disponible para
        # credenciales nuevas (404 verificado el 2026-09-23, con la propia API
        # recomendando gemini-3.6-flash). La cadena arranca por el modelo vigente y
        # mantiene los alias "-latest" detrás para no depender de un nombre puntual.
        models_to_try = [self.gemini_model, "gemini-3.6-flash", "gemini-flash-latest", "gemini-pro-latest"]
        last_exc = None
        seen_models = set()
        for model in models_to_try:
            if not model or model in seen_models:
                continue
            seen_models.add(model)
            try:
                response = self.session.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    params={"key": self.gemini_api_key},
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()
                text = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text:
                    return text
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
        return ""

    def _ask_gemini_for_alternatives(self, url: str, failed_candidates: Optional[List[str]] = None) -> List[str]:
        """Ask Gemini for up to 10 probable alternative URLs when local rules fail."""
        if not self.gemini_api_key:
            logger.info("GEMINI_API_KEY no configurada; se omite fallback a Gemini para %s", url)
            return []

        failed = failed_candidates or []
        prompt = (
            "Eres un asistente de descubrimiento web para instituciones públicas. "
            "Dada la URL original que no responde, genera un JSON válido con hasta 10 URL alternativas "
            "más probables, priorizando el mismo dominio institucional, www, TLDs comunes (.org, .com, .bo, .gob.bo, .edu.bo), "
            "y páginas de inicio o rutas comunes, sin incluir explicaciones. "
            f"URL original: {url}. "
            f"Candidatos ya fallidos: {failed}."
            "Responde solo con un array JSON de strings."
        )

        try:
            text = self._generate_gemini_content(prompt)
            if not text:
                return []
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                cleaned = cleaned.rstrip("`").strip()
            candidates = json.loads(cleaned)
            if not isinstance(candidates, list):
                return []
            normalized = []
            seen = set()
            for item in candidates:
                if not isinstance(item, str):
                    continue
                value = self._normalize_candidate_url(item)
                if value and value not in seen and value != url:
                    seen.add(value)
                    normalized.append(value)
            return normalized[:10]
        except Exception as exc:  # pragma: no cover - external service failure
            logger.warning("Gemini fallback failed for %s: %s", url, exc)
            return []

    def _ask_gemini_for_url_verdict(self, url: str, failed_candidates: Optional[List[str]] = None) -> Dict[str, Any]:
        """Ask Gemini for a final verdict: moved, not found, or same URL likely exists."""
        if not self.gemini_api_key:
            return {
                "status": "skipped",
                "best_url": None,
                "reason": "No hay clave Gemini configurada para validar si la URL cambió o dejó de existir.",
                "alternatives": [],
            }

        failed = failed_candidates or []
        prompt = (
            "Eres un analista experto en portales web institucionales y financieros. "
            "Dada una URL original que no responde o da error de conexión, investiga e indica: "
            "(1) Si la URL o sitio migró a un nuevo dominio, subdominio o portal (status: 'moved'), proporcionando la nueva URL exacta en 'best_url'. "
            "(2) Si la institución o recurso web de plano ya no existe (status: 'not_found'). "
            "(3) Si existen URLs alternativas en la web con otro nombre, estructura o dominio institucional (status: 'exists' o 'moved'), incluyéndolas en 'alternatives'. "
            "Devuelve SOLO un JSON válido con este esquema exacto: "
            "{\"status\": \"moved\"|\"not_found\"|\"unknown\"|\"exists\", "
            "\"best_url\": string|null, \"reason\": string, \"alternatives\": [string]} "
            f"URL original analizada: {url}. "
            f"Candidatos probados que ya fallaron: {failed[:15]}. "
            "No agregues texto explicativo fuera del JSON."
        )

        try:
            text = self._generate_gemini_content(prompt)
            if not text:
                return {"status": "unknown", "best_url": None, "reason": "Gemini no devolvió respuesta útil.", "alternatives": []}
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                cleaned = cleaned.rstrip("`").strip()
            verdict = json.loads(cleaned)
            if not isinstance(verdict, dict):
                return {"status": "unknown", "best_url": None, "reason": "Gemini devolvió una respuesta no válida.", "alternatives": []}
            status = verdict.get("status", "unknown")
            best_url = verdict.get("best_url")
            reason = verdict.get("reason") or "No pudimos determinar con seguridad si la URL cambió o no existe."
            alternatives = verdict.get("alternatives") or []
            normalized = []
            seen = set()
            for item in alternatives:
                if not isinstance(item, str):
                    continue
                value = self._normalize_candidate_url(item)
                if value and value not in seen and value != url:
                    seen.add(value)
                    normalized.append(value)
            if best_url is not None:
                best_url = self._normalize_candidate_url(best_url) or best_url
            return {
                "status": status if status in {"moved", "not_found", "unknown", "exists"} else "unknown",
                "best_url": best_url,
                "reason": reason,
                "alternatives": normalized[:5],
            }
        except Exception as exc:  # pragma: no cover - external service failure
            logger.warning("Gemini verdict failed for %s: %s", url, exc)
            return {"status": "unknown", "best_url": None, "reason": f"La consulta a Gemini falló: {exc}", "alternatives": []}

    def _probe_gemini_alternatives(self, url: str) -> List[Dict[str, Any]]:
        """Query Gemini and probe each returned candidate, preserving source metadata.

        Intercambio Gemini <-> motor de variantes: Gemini suele acertar la institución
        (o su sucesora) pero se equivoca en el dominio exacto — TLD, con/sin ``www``,
        con/sin ruta. En vez de descartar un candidato apenas su URL literal no
        responde, se lo vuelve a pasar por el motor local de variantes
        (``_generate_url_variants``) para intentar encontrar la URL real por
        permutación mecánica antes de darlo por muerto.
        """
        failed_candidates = [candidate for candidate in self._generate_url_variants(url) if candidate != url]
        gemini_candidates = self._ask_gemini_for_alternatives(url, failed_candidates)
        results = []
        seen = {url}
        for candidate in gemini_candidates:
            probe = self.probe_url_variant(candidate)
            probe["source"] = "gemini"
            probe["fallback_method"] = "gemini"
            results.append(probe)
            seen.add(candidate)
            if probe.get("reachable"):
                continue
            for variant in self._generate_url_variants(candidate):
                if variant in seen:
                    continue
                seen.add(variant)
                vprobe = self.probe_url_variant(variant)
                vprobe["source"] = "gemini+variant"
                vprobe["fallback_method"] = "gemini+variant"
                vprobe["gemini_seed"] = candidate
                results.append(vprobe)
        return results

    def _try_url_variants(self, url: str) -> Optional[str]:
        """Generate simple URL variants and return the first reachable candidate or None.

        Variants attempted:
        - https <-> http
        - with/without www
        - root domain (strip path)
        - simple TLD swaps among .com/.org/.bo when applicable
        - remove or add trailing slash
        """
        results = self.probe_url_variants(url)
        first = next((item['url'] for item in results if item['reachable']), None)
        if first:
            return first

        gemini_results = self._probe_gemini_alternatives(url)
        first_gemini = next((item['url'] for item in gemini_results if item.get('reachable')), None)
        return first_gemini

    def _generate_url_variants(self, url: str) -> List[str]:
        parsed = urlparse(url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        path = parsed.path or ""

        candidates: List[str] = []

        def build(sch, nloc, pth):
            base = f"{sch}://{nloc}"
            if pth:
                if not pth.startswith('/'):
                    pth = '/' + pth
                return base + pth
            return base

        # scheme swaps
        schemes = [scheme]
        schemes += ["https" if scheme == "http" else "http"]

        # www variants
        if netloc.startswith('www.'):
            netlocs = [netloc, netloc[4:]]
        else:
            netlocs = [netloc, f"www.{netloc}"]

        # Common domain endings: keep the name and vary the full suffix rather
        # than creating malformed values such as example.org.com.
        host_name = netloc[4:] if netloc.startswith('www.') else netloc
        labels = host_name.split('.')
        stem = labels[0] if labels else host_name
        domain_suffixes = ['.org', '.bo', '.com', '.org.bo', '.com.bo', '.net', '.gob.bo', '.edu.bo']
        generated_netlocs = [f'{stem}{suffix}' for suffix in domain_suffixes]
        for candidate_n in generated_netlocs:
            if candidate_n not in netlocs:
                netlocs.append(candidate_n)
            if f'www.{candidate_n}' not in netlocs:
                netlocs.append(f'www.{candidate_n}')

        # create variants: root and original path
        for sch in schemes:
            for nloc in netlocs:
                # original path
                candidates.append(build(sch, nloc, path))
                # root
                candidates.append(build(sch, nloc, ""))
                # trailing slash variants
                candidates.append(build(sch, nloc, path.rstrip('/') + '/'))

        # dedupe while preserving order
        seen = set()
        deduped = []
        for c in candidates:
            if c and c not in seen and c != url:
                seen.add(c)
                deduped.append(c)

        return deduped

    def probe_url_variants(self, url: str) -> List[Dict[str, Any]]:
        """Probe every generated URL variant and return inspectable results."""
        return [self.probe_url_variant(candidate) for candidate in self._generate_url_variants(url)]

    def probe_url_variant(self, candidate: str) -> Dict[str, Any]:
        """Probe one candidate URL and return a UI-friendly diagnostic."""
        try:
            ok, status, _ = self.fetch_head(candidate)
            if ok:
                return {'url': candidate, 'reachable': True, 'status': status, 'reason': 'Respuesta HTTP válida en HEAD'}
            ok2, status2, _ = self.fetch_html(candidate)
            if ok2:
                return {'url': candidate, 'reachable': True, 'status': status2, 'reason': 'Respuesta HTTP válida en GET'}
            return {'url': candidate, 'reachable': False, 'status': status2 or status or 0, 'reason': 'No respondió con contenido accesible'}
        except requests_exceptions.RequestException as exc:
            return {'url': candidate, 'reachable': False, 'status': 0, 'reason': self._classify_request_error(exc)}
        except Exception as exc:
            return {'url': candidate, 'reachable': False, 'status': 0, 'reason': str(exc) or 'Error desconocido'}

    def _record_moved_url(self, original: str, resolved: str, confidence: float = 0.8) -> None:
        try:
            cfg_dir = Path.cwd() / 'config'
            cfg_dir.mkdir(parents=True, exist_ok=True)
            path = cfg_dir / 'moved_urls.json'
            data = []
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                except Exception:
                    data = []

            entry = {
                'original': original,
                'resolved': resolved,
                'confidence': confidence,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            data.append(entry)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as e:
            logger.warning('No se pudo registrar moved_urls.json: %s', e)
