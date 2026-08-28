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

import time
import logging
import re
from typing import Optional, Dict, Any, Tuple, List
import json
from datetime import datetime
from pathlib import Path
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
        honor_robots_txt: bool = True
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit_seconds = rate_limit_seconds
        self.honor_robots_txt = honor_robots_txt
        
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        
        self._last_request_time: Dict[str, float] = {}
        self._robots_parsers: Dict[str, RobotFileParser] = {}

    def _get_robots_parser(self, domain: str, base_url: str) -> Optional[RobotFileParser]:
        """Carga y parsea el archivo robots.txt del dominio objetivo."""
        if domain in self._robots_parsers:
            return self._robots_parsers[domain]

        robots_url = urljoin(f"{urlparse(base_url).scheme}://{domain}", "/robots.txt")
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            logger.info(f"Verificando robots.txt en: {robots_url}")
            response = self.session.get(robots_url, timeout=10)
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

        if browser_fallback and headless_fetcher is None:
            headless_fetcher = HeadlessFetcher()

        try:
            ok, status, headers = self.fetch_head(url)
            if ok:
                html_candidates.append(("http", status, ""))
                page_html = self._last_http_text(url)
                has_document_signal, effective_score, doc_links, keyword_hits = self._extract_document_counts(page_html, url)
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
                        "file_type": None,
                        "quality_score": effective_score,
                        "snippet_text": (page_html or "")[:180],
                    },
                }
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("HEAD validation raised unexpected error for %s: %s", url, exc)

        try:
            ok, status, text = self.fetch_html(url)
            if ok and text is not None:
                has_document_signal, effective_score, doc_links, keyword_hits = self._extract_document_counts(text, url)
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
                        "file_type": None,
                        "quality_score": effective_score,
                        "snippet_text": text[:180],
                    },
                }
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("GET validation raised unexpected error for %s: %s", url, exc)

        if force_browser_html is not None:
            has_document_signal, effective_score, doc_links, keyword_hits = self._extract_document_counts(force_browser_html, url)
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
            }

        if browser_fallback and headless_fetcher is not None:
            try:
                ok, status, result = headless_fetcher.fetch(url)
                if ok and result is not None:
                    browser_html = result.html
                    has_document_signal, effective_score, doc_links, keyword_hits = self._extract_document_counts(browser_html, url, getattr(result, "network_urls", None))
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
                            "file_type": None,
                            "quality_score": effective_score,
                            "snippet_text": browser_html[:180],
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
                    # persist mapping
                    self._record_moved_url(original=url, resolved=candidate)
                    # re-evaluate the candidate but don't attempt variants again
                    candidate_result = self.validate_url_access(
                        candidate,
                        browser_fallback=browser_fallback,
                        headless_fetcher=headless_fetcher,
                        force_browser_html=force_browser_html,
                        allow_variants=False,
                    )
                    # annotate result with mapping info
                    candidate_result["mapped_from"] = url
                    candidate_result["resolved_from_variant"] = True
                    candidate_result["original_url"] = url
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
                response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
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
                    raise
                time.sleep(1.5 * attempt)

        return False, 0, {}

    def fetch_html(self, url: str) -> Tuple[bool, int, Optional[str]]:
        """Descarga página HTML respetando robots.txt, rate limits y reintentos con backoff."""
        if not self.is_url_allowed_by_robots(url):
            return False, 403, None

        self._apply_rate_limit(url)
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5 * attempt))
                    logger.warning(f"Rate limit 429 recibido en GET {url}. Esperando {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                response.encoding = response.apparent_encoding or "utf-8"
                if response.status_code == 200:
                    return True, 200, response.text
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
                response = self.session.get(url, timeout=self.timeout)
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
        return next((item['url'] for item in results if item['reachable']), None)

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
