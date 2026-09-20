"""Consumo declarativo de endpoints de API JSON en el pipeline de descubrimiento (B-33a).

Permite que fuentes basadas en portales SPA o APIs REST (como Strapi v4, CKAN u OData)
declaren sus endpoints estructurados en la sección `crawl.api_endpoints` de su archivo YAML.
Realiza un barrido recursivo del payload JSON para identificar y extraer candidatos de
descarga (`DiscoveredCandidate`) con procedencia `url_origin="api"`.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

from crawler.core.api_detector import RobotsGate
from crawler.core.discovery import DiscoveredCandidate

logger = logging.getLogger(__name__)


class ApiConsumer:
    """Consumidor declarativo de endpoints de API para el motor de descubrimiento."""

    def __init__(
        self,
        base_url: str,
        allowed_domains: List[str],
        allowed_extensions: List[str],
        is_url_excluded_cb: Optional[Callable[[str], bool]] = None,
        rate_limit_per_second: float = 1.0,
        timeout: int = 15,
        user_agent: str = "DataxProspectorBot/1.0 (+api-consumer)",
    ):
        self.base_url = base_url
        self.allowed_domains = {d.lower() for d in allowed_domains}
        self.allowed_extensions = {e.lower().lstrip(".") for e in allowed_extensions}
        self.is_url_excluded_cb = is_url_excluded_cb
        self.rate_limit_per_second = rate_limit_per_second
        self.timeout = timeout
        self.user_agent = user_agent
        self.robots_gate = RobotsGate(user_agent=user_agent)

    def _is_domain_allowed(self, url: str) -> bool:
        netloc = urlparse(url).netloc.lower()
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        if not netloc:
            return False
        return netloc in self.allowed_domains or netloc.removeprefix("www.") in self.allowed_domains

    def extract_candidates_from_payload(
        self,
        payload: Any,
        endpoint_url: str,
        seen_urls: Optional[Set[str]] = None,
    ) -> List[DiscoveredCandidate]:
        """Recorre recursivamente cualquier estructura de datos JSON y extrae URLs de documentos."""
        discovered: List[DiscoveredCandidate] = []
        if seen_urls is None:
            seen_urls = set()

        def _traverse(node: Any, parent_key: str = "", context_title: str = ""):
            if isinstance(node, dict):
                # Heurística de título si existe en el objeto actual
                current_title = (
                    node.get("titulo")
                    or node.get("title")
                    or node.get("name")
                    or node.get("nombre")
                    or context_title
                )
                for k, v in node.items():
                    _traverse(v, parent_key=k, context_title=str(current_title) if current_title else "")
            elif isinstance(node, list):
                for item in node:
                    _traverse(item, parent_key=parent_key, context_title=context_title)
            elif isinstance(node, str):
                val = node.strip()
                if not val or len(val) < 4:
                    return

                # Descartar nombres de archivo sueltos que no sean rutas o URLs (ej. campo 'name': 'documento.pdf')
                if "/" not in val:
                    return

                # Comprobar si termina o contiene extensiones permitidas
                parsed_val = urlparse(val)
                path = parsed_val.path.lower()
                _, ext = os.path.splitext(path)
                clean_ext = ext.lstrip(".")

                if clean_ext in self.allowed_extensions:
                    resolved = urljoin(endpoint_url, val)
                    if resolved in seen_urls:
                        return
                    if not self._is_domain_allowed(resolved):
                        return
                    if self.is_url_excluded_cb and self.is_url_excluded_cb(resolved):
                        return

                    seen_urls.add(resolved)
                    anchor = context_title or os.path.basename(path) or f"api_resource_{len(seen_urls)}"
                    discovered.append(
                        DiscoveredCandidate(
                            url=resolved,
                            url_origin="api",
                            anchor_text=str(anchor),
                            context_text=f"Endpoint: {endpoint_url} (campo '{parent_key}')",
                            dataset_id="",
                            file_type=clean_ext,
                        )
                    )

        _traverse(payload)
        return discovered

    def discover_from_endpoints(
        self,
        api_endpoints_config: List[Dict[str, Any]],
    ) -> List[DiscoveredCandidate]:
        """Itera sobre la lista declarativa de endpoints y extrae todos los candidatos disponibles."""
        if not api_endpoints_config:
            return []

        all_candidates: List[DiscoveredCandidate] = []
        headers = {"User-Agent": self.user_agent}

        for ep_cfg in api_endpoints_config:
            raw_url = ep_cfg.get("url")
            if not raw_url:
                continue

            pagination_type = str(ep_cfg.get("pagination", "none")).lower()
            max_pages = int(ep_cfg.get("max_pages", 10))
            if max_pages <= 0:
                max_pages = 10
            # Tope absoluto de seguridad contra desbordes
            max_pages = min(max_pages, 50)

            logger.info(
                f"[ApiConsumer] Procesando endpoint de API: {raw_url} (tipo paginación: {pagination_type}, max_pages: {max_pages})"
            )

            endpoint_seen_urls: Set[str] = set()
            current_page = 1
            consecutive_empty_pages = 0

            while current_page <= max_pages:
                # Construir URL para la página actual
                target_url = self._build_page_url(raw_url, pagination_type, current_page)

                # Comprobación de robots.txt
                if not self.robots_gate.allowed(target_url):
                    logger.warning(f"[ApiConsumer] URL bloqueada por robots.txt: {target_url}")
                    break

                try:
                    resp = requests.get(target_url, headers=headers, timeout=self.timeout)
                    if resp.status_code != 200:
                        logger.warning(
                            f"[ApiConsumer] HTTP {resp.status_code} al consultar API página {current_page}: {target_url} (fin de paginación o error del servidor)"
                        )
                        break

                    try:
                        payload = resp.json()
                    except Exception as json_err:
                        logger.warning(f"[ApiConsumer] Respuesta no es JSON válido en {target_url}: {json_err}")
                        break

                    page_candidates = self.extract_candidates_from_payload(
                        payload, endpoint_url=target_url, seen_urls=endpoint_seen_urls
                    )
                    logger.info(
                        f"[ApiConsumer] Página {current_page} de {raw_url}: {len(page_candidates)} candidatos encontrados."
                    )

                    if not page_candidates:
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= 2:
                            break
                    else:
                        consecutive_empty_pages = 0
                        all_candidates.extend(page_candidates)

                    # Verificar fin de paginación
                    if pagination_type == "strapi_v4":
                        page_count = None
                        if isinstance(payload, dict):
                            meta_pag = payload.get("meta", {}).get("pagination", {})
                            page_count = meta_pag.get("pageCount")
                        if page_count is not None and current_page >= page_count:
                            logger.info(f"[ApiConsumer] Alcanzada última página Strapi ({current_page}/{page_count}).")
                            break
                    elif pagination_type == "none":
                        break

                    current_page += 1
                    if self.rate_limit_per_second > 0:
                        time.sleep(1.0 / self.rate_limit_per_second)

                except Exception as exc:
                    logger.error(f"[ApiConsumer] Error al consumir API {target_url}: {exc}")
                    break

        return all_candidates

    def _build_page_url(self, raw_url: str, pagination_type: str, page: int) -> str:
        if pagination_type != "strapi_v4" or page <= 1:
            return raw_url

        parsed = urlparse(raw_url)
        q_params = dict(parse_qsl(parsed.query))
        q_params["pagination[page]"] = str(page)
        new_query = urlencode(q_params)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
