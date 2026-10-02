"""
crawler/core/relocation_manager.py
==================================
Administrador central de reubicaciones de archivos, redirecciones y herencia institucional.

Cubre dos niveles de reubicación:
1. Mismo dominio / misma URL:
   - Seguimiento de redirecciones HTTP (301, 302, 307, 308).
   - Generación heurística de variaciones de ruta (subcarpetas comunes, normalización de separadores, extensiones).
2. Dominios sucesores / herencia cross-domain:
   - Integración activa de `config/moved_urls.json`.
   - Registro de sucesiones institucionales históricas y autorizadas (ej. SPVS -> ASFI/APS, SBEF -> ASFI, CADEXCO -> cadexco.bo, FUNDEMPRESA -> SEPREC).
   - Traducción de URLs antiguas a rutas en dominios sucesores.
   - Validación de dominios autorizados bajo salvaguardas D-01, D-14, D-17 y D-18.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import unicodedata
from urllib.parse import urlparse, urlunparse, quote, unquote

import requests

logger = logging.getLogger(__name__)


# Sucesiones institucionales conocidas en el Estado Plurinacional de Bolivia
# y migraciones de portales documentadas.
CANONICAL_SUCCESSIONS: Dict[str, Dict[str, Any]] = {
    "spvs": {
        "predecessor": "Superintendencia de Pensiones, Valores y Seguros (SPVS)",
        "successors": [
            {
                "entity": "Autoridad de Supervisión del Sistema Financiero (ASFI)",
                "domains": ["asfi.gob.bo", "www.asfi.gob.bo"],
                "keywords": ["asfi", "valores", "seguros", "supervision del sistema financiero", "spvs"],
                "path_prefixes": ["/docs/", "/spvs/", "/archivo-historico/", "/regulacion/"],
            },
            {
                "entity": "Autoridad de Fiscalización y Control de Pensiones y Seguros (APS)",
                "domains": ["aps.gob.bo", "www.aps.gob.bo"],
                "keywords": ["aps", "pensiones", "seguros", "fiscalizacion", "spvs"],
                "path_prefixes": ["/docs/", "/spvs/", "/archivo-historico/", "/pensiones/"],
            },
        ],
    },
    "sbef": {
        "predecessor": "Superintendencia de Bancos y Entidades Financieras (SBEF)",
        "successors": [
            {
                "entity": "Autoridad de Supervisión del Sistema Financiero (ASFI)",
                "domains": ["asfi.gob.bo", "www.asfi.gob.bo"],
                "keywords": ["asfi", "bancos", "entidades financieras", "sbef"],
                "path_prefixes": ["/docs/", "/sbef/", "/archivo-historico/"],
            },
        ],
    },
    "suptrans": {
        "predecessor": "Superintendencia de Transportes (SUPTRANS)",
        "successors": [
            {
                "entity": "Autoridad de Regulación y Fiscalización de Telecomunicaciones y Transportes (ATT)",
                "domains": ["att.gob.bo", "www.att.gob.bo"],
                "keywords": ["att", "telecomunicaciones", "transportes", "suptrans"],
                "path_prefixes": ["/docs/", "/suptrans/", "/transportes/"],
            },
        ],
    },
    "fundempresa": {
        "predecessor": "Concesionaria del Registro de Comercio (FUNDEMPRESA)",
        "successors": [
            {
                "entity": "Servicio Plurinacional de Registro de Comercio (SEPREC)",
                "domains": ["seprec.gob.bo", "www.seprec.gob.bo"],
                "keywords": ["seprec", "registro de comercio", "estadisticas", "fundempresa"],
                "path_prefixes": ["/estadisticas/", "/biblioteca/", "/memorias/"],
            },
        ],
    },
    "cadexco": {
        "predecessor": "Cámara Departamental de Exportadores de Cochabamba",
        "successors": [
            {
                "entity": "CADEXCO (Nuevo Dominio)",
                "domains": ["cadexco.bo", "www.cadexco.bo"],
                "keywords": ["cadexco", "cochabamba", "exportadores"],
                "path_prefixes": ["/", "/publicaciones/", "/descargas/"],
            },
        ],
    },
    "ibch": {
        "predecessor": "Instituto Boliviano del Cemento y Hormigón",
        "successors": [
            {
                "entity": "IBCH (Nuevo Dominio)",
                "domains": ["ibch.com", "www.ibch.com"],
                "keywords": ["ibch", "cemento", "hormigon", "hormigón"],
                "path_prefixes": ["/", "/publicaciones/", "/descargas/"],
            },
        ],
    },
}


class RelocationManager:
    """Gestiona el conocimiento y las heurísticas de reubicación y herencia de URLs y dominios."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or (Path.cwd() / "config")
        self.moved_urls_path = self.config_dir / "moved_urls.json"
        self._moved_urls: List[Dict[str, Any]] = []
        self._url_mapping_cache: Dict[str, Dict[str, Any]] = {}
        self._domain_mapping_cache: Dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        """Carga y actualiza los mapeos de moved_urls.json en memoria."""
        self._moved_urls = []
        self._url_mapping_cache.clear()
        self._domain_mapping_cache.clear()

        if self.moved_urls_path.exists():
            try:
                data = json.loads(self.moved_urls_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._moved_urls = data
                    for item in data:
                        orig = item.get("original")
                        resolved = item.get("resolved")
                        conf = float(item.get("confidence", 0.0))
                        if orig and resolved and conf >= 0.5:
                            orig_norm = orig.rstrip("/").lower()
                            self._url_mapping_cache[orig_norm] = item
                            orig_unquoted = unquote(orig_norm)
                            if orig_unquoted != orig_norm:
                                self._url_mapping_cache[orig_unquoted] = item
                            # Normalización sin tildes (ej. boletín -> boletin)
                            orig_ascii = re.sub(r'[\u0300-\u036f]', '', unicodedata.normalize('NFD', orig_unquoted))
                            if orig_ascii not in self._url_mapping_cache:
                                self._url_mapping_cache[orig_ascii] = item

                            # Extraer mapeo de dominios
                            parsed_orig = urlparse(orig)
                            parsed_res = urlparse(resolved)
                            if parsed_orig.netloc and parsed_res.netloc:
                                dom_orig = parsed_orig.netloc.lower()
                                dom_res = parsed_res.netloc.lower()
                                if dom_orig != dom_res:
                                    self._domain_mapping_cache[dom_orig] = dom_res
                                    # También sin www si aplica
                                    if dom_orig.startswith("www."):
                                        self._domain_mapping_cache[dom_orig[4:]] = dom_res
            except Exception as exc:
                logger.warning("Error cargando %s: %s", self.moved_urls_path, exc)

    @staticmethod
    def normalize_domain(domain: str) -> str:
        """Normaliza un nombre de dominio (minúsculas, sin puerto, sin esquema ni trailing dots)."""
        d = (domain or "").strip().lower()
        if "://" in d:
            d = urlparse(d).netloc or d
        if "/" in d:
            d = d.split("/")[0]
        if ":" in d:
            d = d.split(":")[0]
        return d.rstrip(".")

    def get_moved_mapping(self, url: str) -> Optional[Dict[str, Any]]:
        """Busca si una URL exacta o su prefijo está registrado como movido con confianza suficiente."""
        if not url:
            return None
        norm_url = url.rstrip("/").lower()
        unquoted = unquote(norm_url)
        ascii_url = re.sub(r'[\u0300-\u036f]', '', unicodedata.normalize('NFD', unquoted))

        # 1. Coincidencia exacta de URL (probando raw, unquoted y sin tildes)
        for cand in (norm_url, unquoted, ascii_url):
            if cand in self._url_mapping_cache:
                return self._url_mapping_cache[cand]

        # 2. Coincidencia de prefijo de ruta (ej. /aduana7/content/... -> /com_boletines)
        for orig, mapping in self._url_mapping_cache.items():
            if norm_url.startswith(orig) or unquoted.startswith(orig) or ascii_url.startswith(orig):
                return mapping

        return None

    def get_successor_domains(self, portal_or_domain: str) -> Set[str]:
        """Devuelve el conjunto de dominios sucesores autorizados para un portal o dominio."""
        norm = self.normalize_domain(portal_or_domain)
        clean_domain = norm[4:] if norm.startswith("www.") else norm
        portal_key = clean_domain.split(".")[0] if "." in clean_domain else clean_domain
        successors: Set[str] = set()

        # 1. Desde CANONICAL_SUCCESSIONS
        for key in (norm, clean_domain, portal_key):
            if key in CANONICAL_SUCCESSIONS:
                for succ in CANONICAL_SUCCESSIONS[key]["successors"]:
                    for dom in succ["domains"]:
                        successors.add(self.normalize_domain(dom))

        # 2. Desde moved_urls.json (_domain_mapping_cache)
        for d in (norm, clean_domain):
            if d in self._domain_mapping_cache:
                successors.add(self._domain_mapping_cache[d])
            if f"www.{d}" in self._domain_mapping_cache:
                successors.add(self._domain_mapping_cache[f"www.{d}"])

        return successors

    def is_authorized_successor(self, original_domain: str, candidate_domain: str) -> bool:
        """Verifica si candidate_domain es un sucesor autorizado de original_domain."""
        orig_norm = self.normalize_domain(original_domain)
        cand_norm = self.normalize_domain(candidate_domain)

        if not orig_norm or not cand_norm:
            return False

        orig_clean = orig_norm[4:] if orig_norm.startswith("www.") else orig_norm
        cand_clean = cand_norm[4:] if cand_norm.startswith("www.") else cand_norm

        # Si son del mismo dominio o subdominio, es autorizado
        if cand_clean == orig_clean or cand_clean.endswith("." + orig_clean) or orig_clean.endswith("." + cand_clean):
            return True

        # Sucesores conocidos
        allowed_successors = self.get_successor_domains(orig_norm)
        for succ in allowed_successors:
            succ_clean = succ[4:] if succ.startswith("www.") else succ
            if cand_clean == succ_clean or cand_clean.endswith("." + succ_clean):
                return True

        return False

    def translate_url_to_successor(self, url: str, target_domain: Optional[str] = None) -> List[str]:
        """Traduce una URL antigua hacia uno o varios candidatos en el dominio sucesor."""
        parsed = urlparse(url)
        orig_domain = self.normalize_domain(parsed.netloc)
        candidates: List[str] = []

        # 1. Si existe mapeo específico en moved_urls.json
        mapping = self.get_moved_mapping(url)
        if mapping and mapping.get("resolved"):
            res = mapping["resolved"]
            # Si el mapeo resolvió el dominio o una ruta base
            if res.rstrip("/").lower() != url.rstrip("/").lower():
                candidates.append(res)
                # Si resolvió a nivel dominio, proyectar la ruta original
                parsed_res = urlparse(res)
                if parsed_res.path in ("", "/"):
                    new_url = urlunparse(parsed._replace(netloc=parsed_res.netloc, scheme=parsed_res.scheme or parsed.scheme))
                    if new_url not in candidates:
                        candidates.append(new_url)

        # 2. Dominios sucesores (si se pasó target_domain o se obtienen de la base de conocimiento)
        target_domains = [target_domain] if target_domain else list(self.get_successor_domains(orig_domain))
        
        for dom in target_domains:
            if not dom:
                continue
            dom_norm = self.normalize_domain(dom)
            # Traducción directa de netloc (misma ruta)
            direct_cand = urlunparse(parsed._replace(netloc=dom_norm, scheme="https"))
            if direct_cand not in candidates and direct_cand != url:
                candidates.append(direct_cand)

            # Buscar prefijos históricos sugeridos
            clean_orig = orig_domain[4:] if orig_domain.startswith("www.") else orig_domain
            portal_key = clean_orig.split(".")[0] if "." in clean_orig else clean_orig
            for key in (orig_domain, clean_orig, portal_key):
                if key in CANONICAL_SUCCESSIONS:
                    for succ in CANONICAL_SUCCESSIONS[key]["successors"]:
                        if any(self.normalize_domain(d) == dom_norm for d in succ["domains"]):
                            for prefix in succ.get("path_prefixes", []):
                                prefixed_path = prefix.rstrip("/") + "/" + parsed.path.lstrip("/")
                                prefixed_cand = urlunparse(parsed._replace(netloc=dom_norm, path=prefixed_path, scheme="https"))
                                if prefixed_cand not in candidates:
                                    candidates.append(prefixed_cand)

        return candidates

    def generate_path_variants(self, url: str, period: Optional[str] = None) -> List[str]:
        """
        Genera variaciones heurísticas de ruta para el mismo dominio:
        - Intercambio de carpetas comunes (/archivos/, /docs/, /descargas/, /publicaciones/, etc.)
        - Normalización de separadores ('-', '_', '%20')
        - Variaciones de mayúsculas/minúsculas
        - Variaciones de año/período en el nombre del archivo
        """
        parsed = urlparse(url)
        path = parsed.path
        if not path or path == "/":
            return []

        variants: List[str] = []

        def _add(new_path: str):
            if new_path and new_path != path:
                cand = urlunparse(parsed._replace(path=new_path))
                if cand not in variants and cand != url:
                    variants.append(cand)

        # 1. Separadores entre palabras en el filename: guiones, guiones bajos y espacios
        filename = path.split("/")[-1]
        parent_dir = "/".join(path.split("/")[:-1])
        if parent_dir and not parent_dir.endswith("/"):
            parent_dir += "/"

        if filename:
            # Guiones bajos <-> Guiones <-> Espacios
            if "_" in filename:
                _add(parent_dir + filename.replace("_", "-"))
                _add(parent_dir + filename.replace("_", "%20"))
                _add(parent_dir + filename.replace("_", " "))
            if "-" in filename:
                _add(parent_dir + filename.replace("-", "_"))
                _add(parent_dir + filename.replace("-", "%20"))
                _add(parent_dir + filename.replace("-", " "))
            if "%20" in filename:
                _add(parent_dir + filename.replace("%20", "_"))
                _add(parent_dir + filename.replace("%20", "-"))

            # Minúsculas y mayúsculas
            _add(parent_dir + filename.lower())
            _add(parent_dir + filename.upper())

        # 2. Intercambio de subdirectorios comunes de repositorios documentales
        common_dirs = [
            "/archivos/",
            "/docs/",
            "/descargas/",
            "/publicaciones/",
            "/webdocs/",
            "/content/",
            "/biblioteca/",
            "/memorias/",
            "/documentos/",
            "/boletines/",
        ]
        for cd in common_dirs:
            if cd in path.lower():
                for alt_dir in common_dirs:
                    if alt_dir != cd:
                        new_p = re.sub(re.escape(cd), alt_dir, path, flags=re.IGNORECASE)
                        _add(new_p)

        # 3. Variaciones con año o período si se provee
        if period:
            year = period[:4]
            yy = f"{int(year) % 100:02d}" if year.isdigit() else ""
            if year in path and yy:
                # Reemplazar año de 4 dígitos por 2 dígitos
                _add(path.replace(year, yy))
            elif yy and yy in path:
                # Reemplazar año de 2 dígitos por 4 dígitos
                _add(path.replace(yy, year))

        return variants[:10]

    def follow_redirect(
        self,
        url: str,
        session: Optional[requests.Session] = None,
        timeout: float = 5.0,
        allowed_domains: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Sigue de manera segura redirecciones HTTP (301, 302, 307, 308) y reporta el destino final.
        Valida si el dominio de destino final es el mismo o un sucesor autorizado.
        """
        sess = session or requests.Session()
        result: Dict[str, Any] = {
            "original_url": url,
            "final_url": url,
            "redirected": False,
            "status_code": 0,
            "headers": {},
            "is_authorized": False,
        }

        try:
            # Petición HEAD sin permitir redirects automáticos en el primer salto para auditar
            resp = sess.head(url, timeout=timeout, allow_redirects=True, verify=False)
            result["status_code"] = resp.status_code
            result["final_url"] = resp.url or url
            result["headers"] = dict(resp.headers)
            result["redirected"] = bool(resp.history or result["final_url"] != url)

            # Verificar autorización del dominio final
            final_domain = self.normalize_domain(urlparse(result["final_url"]).netloc)
            orig_domain = self.normalize_domain(urlparse(url).netloc)

            is_auth = False
            if allowed_domains and any(final_domain == ad or final_domain.endswith("." + ad) for ad in allowed_domains):
                is_auth = True
            elif self.is_authorized_successor(orig_domain, final_domain):
                is_auth = True

            result["is_authorized"] = is_auth
        except Exception as exc:
            logger.debug("Error siguiendo redirección para %s: %s", url, exc)
            result["error"] = str(exc)

        return result
