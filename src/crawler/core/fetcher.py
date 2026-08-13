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
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import requests

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
        except Exception as e:
            logger.warning(f"Error al obtener robots.txt de [{domain}]: {e}")

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

                return (response.status_code == 200), response.status_code, dict(response.headers)
            except Exception as e:
                logger.warning(f"HEAD {url} intento {attempt}/{self.max_retries} falló: {e}")
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
            except Exception as e:
                logger.warning(f"GET HTML {url} intento {attempt}/{self.max_retries} falló: {e}")
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
            except Exception as e:
                logger.warning(f"GET bytes {url} intento {attempt}/{self.max_retries} falló: {e}")
                time.sleep(1.5 * attempt)

        return False, 0, None
