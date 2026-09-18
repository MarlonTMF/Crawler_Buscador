"""Detección de APIs y su documentación en sitios institucionales.

Combina dos señales, tal como se acordó con el usuario:

1. Sondeo activo de rutas conocidas (REST/GraphQL/WordPress/OpenAPI) contra el
   dominio del sitio.
2. Tráfico de red observado al renderizar la página con Playwright
   (``HeadlessFetcher``), que revela llamadas AJAX/fetch que la web hace en
   segundo plano y que un sondeo estático nunca vería.

No reemplaza el pipeline de "document_evidence" existente: genera evidencia
independiente (``api_evidence``) pensada para un reporte aparte dirigido al
cliente (ver ``generate_api_report.py``).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "DataxProspectorBot/1.0 (+api-report)"

# Rutas comunes donde suele vivir una API. Se sondean contra la raíz del dominio.
KNOWN_API_PATHS = [
    "/api",
    "/api/",
    "/api/v1",
    "/api/v2",
    "/api/v3",
    "/rest",
    "/rest/v1",
    "/services",
    "/service",
    "/ws",
    "/ws/v1",
    "/webservice",
    "/graphql",
    "/wp-json",
    "/wp-json/wp/v2",
    "/jsonapi",  # Drupal
    "/api.json",
    "/data/api",
    "/_api",  # SharePoint
    "/api/health",
    "/odata",
    "/odata/v1",
    # Portales de datos abiertos / geográficos, comunes en reguladores y municipios.
    "/arcgis/rest/services",
    "/server/rest/services",
    "/api/3/action/package_list",  # CKAN
    # SOAP legacy, todavía frecuente en sistemas de gobierno bolivianos.
    "/service.asmx?wsdl",
    "/api.asmx?wsdl",
    "/ws.asmx?wsdl",
]

# Rutas donde suele publicarse documentación de API (Swagger/OpenAPI/Redoc/etc).
KNOWN_DOC_PATHS = [
    "/swagger.json",
    "/swagger/index.html",
    "/swagger-ui.html",
    "/swagger-ui/",
    "/swagger-ui/index.html",
    "/v1/swagger.json",
    "/v2/swagger.json",
    "/openapi.json",
    "/openapi.yaml",
    "/api-docs",
    "/api/docs",
    "/api/documentation",
    "/docs/api",
    "/redoc",
    "/graphql/playground",
    "/.well-known/openapi.json",
]

# Subdominios donde las instituciones suelen alojar la API por separado del sitio web.
API_SUBDOMAIN_PREFIXES = ["api", "data", "datos", "servicios", "ws", "webservices"]

# Palabras clave que, si aparecen en un enlace o en su texto, sugieren que
# apunta a documentación de API.
DOC_KEYWORDS = [
    "swagger", "openapi", "redoc", "api docs", "api-docs", "documentacion api",
    "documentación api", "api documentation", "developers", "desarrolladores",
    "postman", "graphql playground", "api reference",
]

# Fragmentos de path/host que sugieren que una URL de red es una llamada de API
# (usado tanto para sondeo activo como para tráfico capturado por Playwright).
API_URL_HINTS = [
    "/api/", "/api.", "/rest/", "/graphql", "/wp-json/", "/v1/", "/v2/", "/v3/",
    ".json", "/odata/", "api.",
]

JSON_LIKE_CONTENT_TYPES = ("application/json", "application/ld+json", "application/vnd.api+json")


@dataclass
class ApiEndpointEvidence:
    url: str
    status: Optional[int]
    content_type: Optional[str]
    source: str  # "probe" | "network"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "content_type": self.content_type,
            "source": self.source,
            "note": self.note,
        }


@dataclass
class ApiDocEvidence:
    url: str
    source: str  # "probe" | "link"
    title: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"url": self.url, "source": self.source, "title": self.title}


@dataclass
class ApiSiteReport:
    base_url: str
    endpoints: List[ApiEndpointEvidence] = field(default_factory=list)
    documentation: List[ApiDocEvidence] = field(default_factory=list)
    robots_blocked_paths: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    network_capture_attempted: bool = False
    network_capture_ok: bool = False

    @property
    def has_api(self) -> bool:
        return len(self.endpoints) > 0

    @property
    def has_documentation(self) -> bool:
        return len(self.documentation) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "has_api": self.has_api,
            "has_documentation": self.has_documentation,
            "endpoints": [e.to_dict() for e in self.endpoints],
            "documentation": [d.to_dict() for d in self.documentation],
            "robots_blocked_paths": self.robots_blocked_paths,
            "errors": self.errors,
            "network_capture_attempted": self.network_capture_attempted,
            "network_capture_ok": self.network_capture_ok,
        }


def _looks_like_api_url(url: str) -> bool:
    lower = url.lower()
    return any(hint in lower for hint in API_URL_HINTS)


def _registrable_domain(netloc: str) -> str:
    """Aproximación simple: quita 'www.' y se queda con las últimas 2-3 etiquetas.

    No es un parser de PSL completo, pero alcanza para distinguir
    'www.finrural.org.bo' de 'player.vimeo.com' o de 'openknowledge.worldbank.org'.
    """
    host = netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # dominios tipo .org.bo / .gob.bo / .com.bo necesitan 3 etiquetas para ser comparables
    if parts[-2] in {"org", "gob", "com", "net", "edu"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _is_same_site(url: str, base_url: str) -> bool:
    """True si ``url`` pertenece al mismo dominio institucional que ``base_url``.

    Se usa para descartar de los "endpoints propios" cosas como widgets de
    terceros (player.vimeo.com, google maps, etc.) que aparecen en el HTML/JS
    de la página pero no son una API de la institución analizada.
    """
    try:
        return _registrable_domain(urlparse(url).netloc) == _registrable_domain(urlparse(base_url).netloc)
    except Exception:
        return False


def _looks_like_api_response(content_type: Optional[str], body_start: str) -> bool:
    if content_type and any(ct in content_type.lower() for ct in JSON_LIKE_CONTENT_TYPES):
        return True
    stripped = body_start.strip()
    return stripped.startswith("{") or stripped.startswith("[")


def _looks_like_doc_response(content_type: Optional[str], body: str) -> bool:
    # No filtramos por content-type: WSDL llega como XML, OpenAPI puede llegar
    # como YAML/JSON/HTML según el servidor. Confiamos en las palabras clave del
    # propio contenido (un swagger.json real siempre trae "openapi"/"swagger" como
    # clave; un WSDL siempre trae la palabra "wsdl").
    lowered = (body or "").lower()
    return any(kw in lowered for kw in (
        "swagger", "openapi", "redoc", "api documentation", "api reference", "wsdl",
        "graphql playground", "\"paths\":", "definitions.json",
    ))


class RobotsGate:
    """Comprueba robots.txt una sola vez por dominio, sin lanzar excepciones."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, timeout: int = 8):
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache: Dict[str, Optional[RobotFileParser]] = {}
        self._lock = threading.Lock()  # se comparte entre hilos cuando se corre con --workers > 1

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            cached = origin in self._cache
            parser = self._cache.get(origin)
        if not cached:
            parser = RobotFileParser()
            try:
                resp = requests.get(urljoin(origin, "/robots.txt"), timeout=self.timeout,
                                     headers={"User-Agent": self.user_agent})
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                else:
                    parser = None
            except Exception:
                parser = None
            with self._lock:
                self._cache[origin] = parser
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return True


def probe_domain_for_apis(
    base_url: str,
    session: Optional[requests.Session] = None,
    timeout: int = 10,
    rate_limit_seconds: float = 0.4,
    robots_gate: Optional[RobotsGate] = None,
    honor_robots_txt: bool = True,
) -> ApiSiteReport:
    """Sondea rutas conocidas de API y de documentación contra ``base_url``."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else base_url.rstrip("/")
    report = ApiSiteReport(base_url=origin)

    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    gate = robots_gate or RobotsGate(user_agent=sess.headers.get("User-Agent", DEFAULT_USER_AGENT))

    # Timeout de conexión más corto que el de lectura: si el servidor ni siquiera
    # acepta la conexión, no tiene sentido esperar el timeout completo por cada
    # una de las ~35 rutas que se sondean.
    request_timeout = (min(5, timeout), timeout)

    # Circuit breaker: algunos sitios .gob.bo aceptan la conexión pero nunca
    # responden (drop silencioso), lo que hace que CADA ruta agote el timeout.
    # Si varias rutas seguidas fallan por error de conexión (no HTTP 4xx/5xx),
    # asumimos que el dominio no va a responder y dejamos de insistir.
    consecutive_failures = 0
    circuit_open = False
    CIRCUIT_BREAKER_THRESHOLD = 3

    def _get(path_or_url: str, is_absolute: bool = False):
        nonlocal consecutive_failures, circuit_open
        if circuit_open:
            return None
        target = path_or_url if is_absolute else urljoin(origin + "/", path_or_url.lstrip("/"))
        if honor_robots_txt and not gate.allowed(target):
            report.robots_blocked_paths.append(target)
            return None
        last_exc = None
        for attempt in range(2):  # 1 reintento: los sitios .gob.bo suelen ser inestables.
            try:
                resp = sess.get(target, timeout=request_timeout, allow_redirects=True)
                consecutive_failures = 0
                return resp
            except Exception as exc:
                last_exc = exc
                continue
            finally:
                if rate_limit_seconds:
                    time.sleep(rate_limit_seconds)
        report.errors.append(f"{target}: {last_exc}")
        consecutive_failures += 1
        if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD and not circuit_open:
            circuit_open = True
            report.errors.append(
                f"{origin}: se abandonó el sondeo tras {CIRCUIT_BREAKER_THRESHOLD} fallos de conexión seguidos "
                "(el sitio probablemente no responde)."
            )
        return None

    seen_endpoints = set()
    for path in KNOWN_API_PATHS:
        resp = _get(path)
        if resp is None:
            continue
        content_type = resp.headers.get("Content-Type")
        body_start = resp.text[:400] if resp.text else ""
        if resp.status_code < 400 and (_looks_like_api_response(content_type, body_start) or resp.status_code in (401, 403)):
            note = "requiere autenticación" if resp.status_code in (401, 403) else ""
            if resp.url not in seen_endpoints:
                seen_endpoints.add(resp.url)
                report.endpoints.append(ApiEndpointEvidence(
                    url=resp.url, status=resp.status_code, content_type=content_type,
                    source="probe", note=note,
                ))

    seen_docs = set()
    for path in KNOWN_DOC_PATHS:
        resp = _get(path)
        if resp is None:
            continue
        if resp.status_code < 400:
            content_type = resp.headers.get("Content-Type")
            body = resp.text[:4000] if resp.text else ""
            # OJO: muchos sitios (SPA / servidores mal configurados) devuelven 200 con
            # la portada normal para CUALQUIER ruta ("soft 404"). Por eso exigimos que
            # el contenido realmente mencione swagger/openapi/wsdl, y no solo status 200.
            if _looks_like_doc_response(content_type, body):
                if resp.url not in seen_docs:
                    seen_docs.add(resp.url)
                    title = _extract_title(body) or path
                    report.documentation.append(ApiDocEvidence(url=resp.url, source="probe", title=title))

    if honor_robots_txt is False or gate.allowed(origin):
        subdomain_endpoints = _probe_api_subdomains(origin, sess, timeout, rate_limit_seconds, gate, honor_robots_txt, report)
        for item in subdomain_endpoints:
            if item.url not in seen_endpoints:
                seen_endpoints.add(item.url)
                report.endpoints.append(item)

    return report


def _probe_api_subdomains(
    origin: str,
    sess: requests.Session,
    timeout: int,
    rate_limit_seconds: float,
    gate: "RobotsGate",
    honor_robots_txt: bool,
    report: "ApiSiteReport",
) -> List["ApiEndpointEvidence"]:
    """Prueba subdominios típicos (api.<dominio>, data.<dominio>, ...) además del dominio principal."""
    parsed = urlparse(origin)
    host = parsed.netloc
    root = host[4:] if host.startswith("www.") else host
    if not root or root.count(".") < 1:
        return []

    found: List[ApiEndpointEvidence] = []
    for prefix in API_SUBDOMAIN_PREFIXES:
        candidate_root = f"{parsed.scheme}://{prefix}.{root}"
        if candidate_root == origin:
            continue
        if honor_robots_txt and not gate.allowed(candidate_root + "/"):
            continue
        try:
            resp = sess.get(candidate_root + "/", timeout=(min(5, timeout), timeout), allow_redirects=True)
        except Exception:
            continue
        finally:
            if rate_limit_seconds:
                time.sleep(rate_limit_seconds)
        if resp.status_code < 400:
            content_type = resp.headers.get("Content-Type")
            body_start = resp.text[:400] if resp.text else ""
            if _looks_like_api_response(content_type, body_start):
                found.append(ApiEndpointEvidence(
                    url=resp.url, status=resp.status_code, content_type=content_type,
                    source="subdomain", note=f"subdominio {prefix}.{root} responde JSON",
                ))
    return found


def scan_html_for_api_links(html: Optional[str], base_url: str) -> Dict[str, List[Dict[str, Any]]]:
    """Busca en el HTML enlaces que sugieran endpoints de API o su documentación."""
    endpoints: List[Dict[str, Any]] = []
    docs: List[Dict[str, Any]] = []
    if not html:
        return {"endpoints": endpoints, "documentation": docs}

    pattern = r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    seen_e, seen_d = set(), set()
    for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
        href, anchor_text = match.groups()
        anchor_clean = re.sub(r"<[^>]+>", "", anchor_text).strip()
        try:
            full_url = urljoin(base_url, href)
        except Exception:
            continue
        if not full_url.startswith("http"):
            continue
        lower_href = full_url.lower()
        lower_text = anchor_clean.lower()

        if any(kw in lower_href or kw in lower_text for kw in DOC_KEYWORDS):
            if full_url not in seen_d:
                seen_d.add(full_url)
                docs.append({"url": full_url, "source": "link", "title": anchor_clean[:80] or full_url})
            continue

        # Solo contamos como "API de la institución" enlaces al mismo dominio: un link a
        # una API de terceros (ej. un repositorio externo) no es la API del sitio analizado.
        if _looks_like_api_url(full_url) and _is_same_site(full_url, base_url):
            if full_url not in seen_e:
                seen_e.add(full_url)
                endpoints.append({"url": full_url, "status": None, "content_type": None,
                                   "source": "link", "note": anchor_clean[:80]})

    return {"endpoints": endpoints, "documentation": docs}


_JS_URL_CALL_PATTERNS = [
    re.compile(r'fetch\(\s*[`"\']([^`"\']+)[`"\']', re.IGNORECASE),
    re.compile(r'axios(?:\.(?:get|post|put|delete|patch))?\(\s*[`"\']([^`"\']+)[`"\']', re.IGNORECASE),
    re.compile(r'\.open\(\s*[`"\']\w+[`"\']\s*,\s*[`"\']([^`"\']+)[`"\']', re.IGNORECASE),  # XMLHttpRequest.open
    re.compile(r'[`"\'](/api/[^`"\'\s]+)[`"\']', re.IGNORECASE),
    re.compile(r'[`"\'](https?://[^`"\'\s]*?/api/[^`"\'\s]*)[`"\']', re.IGNORECASE),
]


def scan_js_bundles_for_api_calls(
    html: Optional[str],
    base_url: str,
    session: Optional[requests.Session] = None,
    timeout: int = 8,
    max_scripts: int = 4,
) -> Dict[str, List[Dict[str, Any]]]:
    """Descarga algunos <script src="..."> de la portada y busca llamadas a API en su código.

    Cubre el caso de las SPA (React/Angular/Vue) cuyas llamadas fetch/axios solo se
    disparan tras interacción del usuario y por eso no aparecen ni en el HTML inicial
    ni en la captura de red de la carga inicial.
    """
    endpoints: List[Dict[str, Any]] = []
    if not html:
        return {"endpoints": endpoints}

    script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html, re.IGNORECASE)
    same_origin = []
    seen_src = set()
    for src in script_srcs:
        try:
            full = urljoin(base_url, src)
        except Exception:
            continue
        if full in seen_src or not full.startswith("http"):
            continue
        seen_src.add(full)
        same_origin.append(full)

    # Priorizamos bundles con nombres típicos de "app principal" sobre vendor/polyfills.
    def _priority(u: str) -> int:
        lower = u.lower()
        if any(kw in lower for kw in ("main", "app", "index")):
            return 0
        if any(kw in lower for kw in ("chunk", "bundle")):
            return 1
        return 2

    same_origin.sort(key=_priority)

    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    seen_endpoints = set()
    for src in same_origin[:max_scripts]:
        try:
            resp = sess.get(src, timeout=(min(5, timeout), timeout))
            if resp.status_code >= 400:
                continue
            code = resp.text[:500_000]  # cap defensivo: algunos bundles pesan varios MB
        except Exception:
            continue

        for pattern in _JS_URL_CALL_PATTERNS:
            for match in pattern.finditer(code):
                candidate = match.group(1)
                if not candidate or candidate.startswith(("data:", "blob:", "#")):
                    continue
                # Plantillas de código sin interpolar (`${var}`, `{{var}}`, `:param`) no son
                # URLs reales que se puedan reportar como endpoint concreto: las descartamos.
                if any(marker in candidate for marker in ("${", "{{", "%7B")):
                    continue
                try:
                    full_url = candidate if candidate.startswith("http") else urljoin(base_url, candidate)
                except Exception:
                    continue
                # Descarta widgets/SDKs de terceros embebidos (Vimeo, YouTube, mapas, analytics...):
                # no son la API de la institución, aunque aparezcan en su bundle JS.
                if full_url in seen_endpoints or not _looks_like_api_url(full_url) or not _is_same_site(full_url, base_url):
                    continue
                seen_endpoints.add(full_url)
                endpoints.append({
                    "url": full_url, "status": None, "content_type": None,
                    "source": "js-bundle", "note": f"referenciado en {src.split('/')[-1]}",
                })

    return {"endpoints": endpoints}


def scan_network_traffic_for_apis(
    network_responses: List[Dict[str, Any]], base_url: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Filtra respuestas de red capturadas por Playwright que parecen llamadas de API.

    Si se pasa ``base_url``, descarta llamadas a dominios de terceros (Google
    Analytics, Facebook Pixel, CDNs de mapas/video, etc.) que no son la API
    de la institución sino de un widget embebido en su página.
    """
    endpoints: List[Dict[str, Any]] = []
    seen = set()
    for item in network_responses or []:
        url = item.get("url") if isinstance(item, dict) else item
        if not url or url in seen:
            continue
        if base_url and not _is_same_site(url, base_url):
            continue
        content_type = item.get("content_type") if isinstance(item, dict) else None
        status = item.get("status") if isinstance(item, dict) else None
        is_json_ct = bool(content_type) and any(ct in content_type.lower() for ct in JSON_LIKE_CONTENT_TYPES)
        if is_json_ct or _looks_like_api_url(url):
            seen.add(url)
            endpoints.append({
                "url": url, "status": status, "content_type": content_type,
                "source": "network", "note": "detectado en tráfico de red al renderizar la página",
            })
    return {"endpoints": endpoints}


def _extract_title(html_fragment: str) -> Optional[str]:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_fragment, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()[:120]
    return None


def merge_reports(probe_report: ApiSiteReport, *extra: Dict[str, List[Dict[str, Any]]]) -> ApiSiteReport:
    """Combina el resultado del sondeo activo con hallazgos de HTML/tráfico de red."""
    seen_endpoints = {e.url for e in probe_report.endpoints}
    seen_docs = {d.url for d in probe_report.documentation}
    for extra_result in extra:
        for e in extra_result.get("endpoints", []) or []:
            if e["url"] not in seen_endpoints:
                seen_endpoints.add(e["url"])
                probe_report.endpoints.append(ApiEndpointEvidence(
                    url=e["url"], status=e.get("status"), content_type=e.get("content_type"),
                    source=e.get("source", "unknown"), note=e.get("note", ""),
                ))
        for d in extra_result.get("documentation", []) or []:
            if d["url"] not in seen_docs:
                seen_docs.add(d["url"])
                probe_report.documentation.append(ApiDocEvidence(
                    url=d["url"], source=d.get("source", "unknown"), title=d.get("title", ""),
                ))
    return probe_report
