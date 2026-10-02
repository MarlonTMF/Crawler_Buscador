"""
Escalera de recuperación de períodos faltantes (B-54).
Recupera períodos faltantes en orden de menor a mayor riesgo:
1. Misma URL conocida anteriormente
2. Plantilla de serie con validación HEAD (D-17)
3. Ruta alterna dentro del mismo dominio (sitemap / buscador / variaciones de ruta)
4. Archivo histórico web (Wayback Machine)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, unquote, urlparse, urljoin, urlunparse

import requests
import urllib3

from crawler.core.fetcher import HttpFetcher
from crawler.core.gap_detector import GapDetector
from crawler.core.relocation_manager import RelocationManager, CANONICAL_SUCCESSIONS
from crawler.core.wayback_engine import query_cdx_snapshots
from crawler.sources.generic_adapter import GenericSourceAdapter

urllib3.disable_warnings()
logger = logging.getLogger(__name__)


class RecoveryRung(IntEnum):
    RUNG_1_KNOWN_URL = 1
    RUNG_2_SERIES_TEMPLATE = 2
    RUNG_3_SAME_DOMAIN_ALTERNATE = 3
    RUNG_4_WAYBACK_ARCHIVE = 4
    RUNG_5_AGENT_GEMINI = 5


@dataclass
class RecoveredPeriod:
    portal: str
    dataset_id: str
    period: str
    recovery_rung: int
    rung_name: str
    url: str
    file_size_bytes: int
    content_sha256: str
    verified_at: str
    status: str = "RECOVERED"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portal": self.portal,
            "dataset_id": self.dataset_id,
            "period": self.period,
            "recovery_rung": self.recovery_rung,
            "rung_name": self.rung_name,
            "url": self.url,
            "file_size_bytes": self.file_size_bytes,
            "content_sha256": self.content_sha256,
            "verified_at": self.verified_at,
            "status": self.status,
            "metadata": self.metadata,
        }


class RecoveryLadder:
    """Implementa la escalera determinista de recuperación de períodos faltantes."""

    # Plantillas de serie conocidas para Escalón 2 (D-17)
    SERIES_TEMPLATES: Dict[Tuple[str, str], List[str]] = {
        ("bcb", "deuda_externa"): [
            "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20{mon}{yy}.pdf",
            "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20{mon}{yyyy}.pdf",
        ],
        ("bcb", "boletines_mensuales"): [
            "https://www.bcb.gob.bo/webdocs/sistema_pagos/Bolet%C3%ADn%20mensual%20{mes_nombre}%20{yyyy}.pdf",
            "https://www.bcb.gob.bo/webdocs/sistema_pagos/Bolet%C3%ADn%20mensual%20SP%20{mes_mayus}%20{yyyy}.pdf",
        ],
        ("asfi", "balance_general"): [
            "https://www.asfi.gob.bo/sites/default/files/2026-07/{yyyymm}_BDR_EstadosFinancieros.zip",
            "https://www.asfi.gob.bo/sites/default/files/2025-08/{yyyymm}_BDR_EstadosFinancieros.xls",
        ],
    }

    MONTH_NAMES_ES = {
        1: ("Enero", "enero", "ENE", "ene"),
        2: ("Febrero", "febrero", "FEB", "feb"),
        3: ("Marzo", "marzo", "MAR", "mar"),
        4: ("Abril", "abril", "ABR", "abr"),
        5: ("Mayo", "mayo", "MAY", "may"),
        6: ("Junio", "junio", "JUN", "jun"),
        7: ("Julio", "julio", "JUL", "jul"),
        8: ("Agosto", "agosto", "AGO", "ago"),
        9: ("Septiembre", "septiembre", "SEP", "sep"),
        10: ("Octubre", "octubre", "OCT", "oct"),
        11: ("Noviembre", "noviembre", "NOV", "nov"),
        12: ("Diciembre", "diciembre", "DIC", "dic"),
    }

    def __init__(
        self,
        fetcher: Optional[HttpFetcher] = None,
        base_output_dir: Path = Path("output"),
        base_config_dir: Path = Path("config"),
        timeout: float = 6.0,
        max_gemini_calls: int = 10,
    ):
        self.fetcher = fetcher or HttpFetcher()
        self.base_output_dir = base_output_dir
        self.base_config_dir = base_config_dir
        self.timeout = timeout
        self.max_gemini_calls = max_gemini_calls
        self.gemini_calls_count = 0
        self._last_download_sample = b""
        self.inheritance_candidates: List[Dict[str, Any]] = []
        self.rechazos_calidad: List[Dict[str, Any]] = []
        self._dataset_sha256_periods: Dict[Tuple[str, str], Dict[str, str]] = {}
        self._recovered_urls: Set[str] = set()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": getattr(self.fetcher, "user_agent", "DataX-Prospector/1.0 (+http://datax.org)")
        })
        self.relocation_manager = RelocationManager(config_dir=self.base_config_dir)
        self._cdx_snapshots_cache: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
        self.dry_run_cdx_queries: Dict[Tuple[str, str], Tuple[str, int]] = {}

    DOCUMENTARY_CONTENT_TYPES = {
        "application/pdf",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/x-zip-compressed",
        "application/x-rar-compressed",
        "text/csv",
        "application/octet-stream",
    }
    DOCUMENTARY_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".zip", ".rar", ".csv"}

    def is_documentary_resource(self, content_type: Optional[str], url: str) -> bool:
        """Verifica si el Content-Type o la extensión de URL corresponden a un tipo documental válido (D-17 / H-2)."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        has_doc_ext = any(path.endswith(ext) for ext in self.DOCUMENTARY_EXTENSIONS)

        if content_type:
            ct = content_type.lower().split(";")[0].strip()
            if ct.startswith("text/html"):
                return False
            if ct in self.DOCUMENTARY_CONTENT_TYPES:
                return True
        return has_doc_ext

    def is_url_already_recovered(self, url: str) -> bool:
        """Verifica si la URL ya fue admitida como recuperación previa en la misma corrida (H-3)."""
        return url in self._recovered_urls

    def verify_content_bytes(self, content: bytes) -> Tuple[int, str]:
        """Calcula el tamaño en bytes y el hash SHA-256 del contenido."""
        if not content:
            return 0, ""
        size = len(content)
        sha256 = hashlib.sha256(content).hexdigest()
        return size, sha256

    def fetch_and_verify(self, url: str) -> Optional[Tuple[int, str]]:
        """Realiza descarga directa verificando bytes > 0, hash SHA-256 y rechazando text/html (H-1)."""
        try:
            r = self._session.get(url, timeout=self.timeout, verify=False, stream=True)
            if r.status_code not in (200, 206):
                return None
            ct = r.headers.get("content-type", "").lower()
            if ct.startswith("text/html"):
                logger.debug("Rechazando recurso por Content-Type text/html en fetch_and_verify: %s", url)
                return None
            hasher = hashlib.sha256()
            total_size = 0
            sample_bytes = bytearray()
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    hasher.update(chunk)
                    total_size += len(chunk)
                    if len(sample_bytes) < 131072:
                        sample_bytes.extend(chunk[: 131072 - len(sample_bytes)])
            self._last_download_sample = bytes(sample_bytes)
            if total_size <= 0:
                return None
            return total_size, hasher.hexdigest()
        except Exception as e:
            logger.debug("Error descargando %s: %s", url, e)
            return None

    def _check_head(self, url: str, require_document_type: bool = False) -> bool:
        """Verifica existencia de recurso con petición HTTP HEAD (status 200, length > 0, tipo documental opcional)."""
        try:
            r = self._session.head(url, timeout=self.timeout, verify=False, allow_redirects=True)
            if r.status_code in (200, 206):
                cl = r.headers.get("content-length")
                if cl is not None and int(cl) <= 0:
                    return False
                if require_document_type:
                    ct = r.headers.get("content-type")
                    if not self.is_documentary_resource(ct, r.url or url):
                        return False
                return True
        except Exception:
            pass
        return False

    def is_url_in_inventory(self, portal: str, canonical_url: str) -> bool:
        """
        Verifica si la URL canónica ya existe registrada en resource_audit_log del inventario del portal.
        Una URL ya presente en el inventario no constituye una recuperación de un período faltante (O-1).
        """
        db_path = self.base_output_dir / portal / "inventory.db"
        if not db_path.exists():
            return False
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                row = cursor.execute(
                    "SELECT 1 FROM resource_audit_log WHERE canonical_url = ? OR canonical_url = ? LIMIT 1",
                    (canonical_url, unquote(canonical_url)),
                ).fetchone()
                return row is not None
        except Exception as e:
            logger.debug("Error verificando inventario para %s: %s", canonical_url, e)
            return False

    def _check_quality_gates(
        self,
        portal: str,
        dataset_id: str,
        period: str,
        url: str,
        content_sha256: str,
        source_rung: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Compuertas de calidad de la Fase 5 (B-59):
        1. Huella SHA-256 repetida: si el mismo content_sha256 ya se asignó a otro período
           del mismo dataset (en esta corrida o en inventory.db), se rechaza.
        2. Año contradictorio: si el nombre del archivo contiene un año de cuatro dígitos
           distinto del período buscado —y no hay otro año que coincida—, se rechaza.
        """
        ds_key = (portal.lower(), dataset_id)
        if ds_key not in self._dataset_sha256_periods:
            self._dataset_sha256_periods[ds_key] = {}

        # 1. Compuerta de huella SHA-256 repetida
        # 1a. En esta corrida
        if content_sha256 and content_sha256 in self._dataset_sha256_periods[ds_key]:
            assigned_p = self._dataset_sha256_periods[ds_key][content_sha256]
            if str(assigned_p) != str(period):
                reason = f"huella_repetida: content_sha256 {content_sha256[:16]}... ya asignado al período {assigned_p} en este dataset"
                self.rechazos_calidad.append({
                    "portal": portal,
                    "dataset_id": dataset_id,
                    "period": period,
                    "url": url,
                    "content_sha256": content_sha256,
                    "source_rung": source_rung,
                    "motivo": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return False, reason

        # 1b. En inventory.db
        if content_sha256:
            db_path = self.base_output_dir / portal / "inventory.db"
            if db_path.exists():
                try:
                    with sqlite3.connect(db_path) as conn:
                        rows = conn.execute(
                            "SELECT period_start, period_end, canonical_url FROM resource_audit_log WHERE dataset_id = ? AND content_sha256 = ? AND status IN ('PROCESADO_EXITOSAMENTE', 'RECUPERADO_VIA_CONTINGENCIA')",
                            (dataset_id, content_sha256),
                        ).fetchall()
                        for p_start, p_end, c_url in rows:
                            p_str = p_start or p_end or ""
                            db_years = set(re.findall(r"(?:^|[^\d])(19\d\d|20\d\d)(?:[^\d]|$)", p_str))
                            curr_years = set(re.findall(r"(?:^|[^\d])(19\d\d|20\d\d)(?:[^\d]|$)", str(period)))
                            if db_years and curr_years and not (db_years & curr_years):
                                reason = f"huella_repetida: content_sha256 {content_sha256[:16]}... ya existe en inventory.db asignado a {p_str}"
                                self.rechazos_calidad.append({
                                    "portal": portal,
                                    "dataset_id": dataset_id,
                                    "period": period,
                                    "url": url,
                                    "content_sha256": content_sha256,
                                    "source_rung": source_rung,
                                    "motivo": reason,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                                return False, reason
                except Exception as e:
                    logger.debug("Error verificando huella repetida en inventory.db: %s", e)

        # 2. Compuerta de año contradictorio en el nombre del archivo
        parsed_url = urlparse(url)
        filename = unquote(parsed_url.path).split("/")[-1]
        file_years = set(re.findall(r"(?:^|[^\d])(19\d\d|20\d\d)(?:[^\d]|$)", filename))
        period_years = set(re.findall(r"(?:^|[^\d])(19\d\d|20\d\d)(?:[^\d]|$)", str(period)))

        if file_years and period_years and not (file_years & period_years):
            reason = f"ano_contradictorio: el archivo '{filename}' contiene año(s) {sorted(file_years)} que no coinciden con el período buscado '{period}'"
            self.rechazos_calidad.append({
                "portal": portal,
                "dataset_id": dataset_id,
                "period": period,
                "url": url,
                "content_sha256": content_sha256,
                "source_rung": source_rung,
                "motivo": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return False, reason

        if content_sha256:
            self._dataset_sha256_periods[ds_key][content_sha256] = str(period)

        return True, None

    def _generate_url_variants(self, url: str) -> List[str]:
        """Genera variantes deterministas de una URL conocida (codificación, separadores, capitalización)."""
        parsed = urlparse(url)
        path = parsed.path
        if "/" in path:
            dirname, filename = path.rsplit("/", 1)
        else:
            dirname, filename = "", path

        fn_variants = set()
        # 1. Variaciones de espacios y codificación
        fn_unquoted = unquote(filename)
        fn_variants.add(filename)
        fn_variants.add(fn_unquoted)
        fn_variants.add(quote(fn_unquoted))
        fn_variants.add(fn_unquoted.replace(" ", "%20"))
        fn_variants.add(fn_unquoted.replace("%20", " "))
        fn_variants.add(fn_unquoted.replace(" ", "+"))
        fn_variants.add(fn_unquoted.replace("+", " "))

        # 2. Variaciones de separadores guion y guion bajo
        more_vars = set()
        for fn in fn_variants:
            if "-" in fn:
                more_vars.add(fn.replace("-", "_"))
                more_vars.add(fn.replace("-", "%20"))
                more_vars.add(fn.replace("-", " "))
            if "_" in fn:
                more_vars.add(fn.replace("_", "-"))
                more_vars.add(fn.replace("_", "%20"))
                more_vars.add(fn.replace("_", " "))
            if "%20" in fn:
                more_vars.add(fn.replace("%20", "-"))
                more_vars.add(fn.replace("%20", "_"))
            if " " in fn:
                more_vars.add(fn.replace(" ", "-"))
                more_vars.add(fn.replace(" ", "_"))
        fn_variants.update(more_vars)

        # 3. Capitalización y extensión
        final_fn_variants = set()
        for fn in fn_variants:
            final_fn_variants.add(fn)
            final_fn_variants.add(fn.upper())
            final_fn_variants.add(fn.lower())
            if fn.endswith(".pdf"):
                final_fn_variants.add(fn[:-4] + ".PDF")
            elif fn.endswith(".PDF"):
                final_fn_variants.add(fn[:-4] + ".pdf")
            if fn.endswith(".xlsx"):
                final_fn_variants.add(fn[:-5] + ".XLSX")
            elif fn.endswith(".XLSX"):
                final_fn_variants.add(fn[:-5] + ".xlsx")

        res_urls = []
        for fn in final_fn_variants:
            new_path = f"{dirname}/{fn}" if dirname else fn
            variant_url = urlunparse((parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment))
            if variant_url not in res_urls:
                res_urls.append(variant_url)

        return res_urls

    def _try_rung_1_known_url(
        self,
        portal: str,
        dataset_id: str,
        period: str,
        periodicity: str,
        known_url: Optional[str] = None,
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 1: Sigue el rastro de la URL conocida anteriormente (B-61 / P-2).
        Estrategias deterministas no especulativas:
          1. Probar la URL directa si no está en inventario.
          2. Seguir la redirección si responde 301/302 (o fue marcada REDIRIGIDA en B-60).
          3. Traducir a dominio sucesor conocido si la entidad migró (D-18 / moved_urls.json).
          4. Si está ELIMINADA (404/410), consultar el directorio superior e identificar archivo del período.
          5. Probar variantes deterministas de la misma URL (codificación, separadores, capitalización).
        """
        candidate_urls: List[str] = []

        if known_url:
            candidate_urls.append(known_url)
        else:
            # 1. Buscar en los resultados de revalidación de B-60
            reval_path = self.base_output_dir / f"revalidacion_{portal}.json"
            year_str = period[:4]
            if reval_path.exists():
                try:
                    reval_data = json.loads(reval_path.read_text(encoding="utf-8"))
                    for item in reval_data.get("results", []):
                        if item.get("dataset_id") == dataset_id or not item.get("dataset_id"):
                            u = item.get("url", "")
                            status = item.get("status", "")
                            if status in ("REDIRIGIDA", "ELIMINADA") and year_str in u:
                                candidate_urls.append(u)
                except Exception as e:
                    logger.debug("Error leyendo revalidación previa de %s: %s", reval_path, e)

            # 2. Buscar en inventory.db registros con URL para este dataset y período
            db_path = self.base_output_dir / portal / "inventory.db"
            if db_path.exists() and not candidate_urls:
                try:
                    conn = sqlite3.connect(db_path)
                    try:
                        cursor = conn.cursor()
                        rows = cursor.execute(
                            "SELECT canonical_url FROM resource_audit_log WHERE dataset_id = ?",
                            (dataset_id,)
                        ).fetchall()
                        for (u,) in rows:
                            if u and year_str in u and u not in candidate_urls:
                                candidate_urls.append(u)
                    finally:
                        conn.close()
                except Exception as e:
                    logger.debug("Error consultando inventario para %s: %s", portal, e)

        for cand_url in candidate_urls:
            # 1. Probar la URL directa si no está en inventario
            if not self.is_url_in_inventory(portal, cand_url) and not self.is_url_already_recovered(cand_url):
                res = self.fetch_and_verify(cand_url)
                if res:
                    size, sha256 = res
                    sample = getattr(self, "_last_download_sample", b"")
                    if sample and not self._verify_institution_content(portal, sample):
                        pass
                    else:
                        ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, cand_url, sha256, 1)
                        if ok_qg:
                            return RecoveredPeriod(
                                portal=portal,
                                dataset_id=dataset_id,
                                period=period,
                                recovery_rung=RecoveryRung.RUNG_1_KNOWN_URL,
                                rung_name="misma_url",
                                url=cand_url,
                                file_size_bytes=size,
                                content_sha256=sha256,
                                verified_at=datetime.now(timezone.utc).isoformat(),
                                metadata={"source_rung": 1, "method": "known_inventory_url"},
                            )

            # 2. Seguimiento de redirecciones HTTP (301/302 hacia URL con 200)
            redir_final_url = None
            if hasattr(self, "relocation_manager"):
                try:
                    allowed_d = set(self._get_allowed_domains(portal))
                    redir = self.relocation_manager.follow_redirect(
                        cand_url, session=self._session, allowed_domains=allowed_d
                    )
                    if redir.get("redirected") and redir.get("is_authorized"):
                        redir_final_url = redir.get("final_url")
                except Exception as e:
                    logger.debug("Error en relocation_manager.follow_redirect para %s: %s", cand_url, e)

            if not redir_final_url:
                try:
                    head_resp = self.fetcher.session.head(cand_url, timeout=self.timeout, allow_redirects=True)
                    if head_resp and head_resp.status_code == 200 and head_resp.history:
                        final_u = str(head_resp.url)
                        if final_u.rstrip("/") != cand_url.rstrip("/"):
                            redir_final_url = final_u
                except Exception as e:
                    logger.debug("HEAD falló para %s: %s", cand_url, e)

            if redir_final_url:
                if not self.is_url_in_inventory(portal, redir_final_url) and not self.is_url_already_recovered(redir_final_url):
                    res = self.fetch_and_verify(redir_final_url)
                    if res:
                        size, sha256 = res
                        sample = getattr(self, "_last_download_sample", b"")
                        if sample and not self._verify_institution_content(portal, sample):
                            continue
                        ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, redir_final_url, sha256, 1)
                        if ok_qg:
                            return RecoveredPeriod(
                                portal=portal,
                                dataset_id=dataset_id,
                                period=period,
                                recovery_rung=RecoveryRung.RUNG_1_KNOWN_URL,
                                rung_name="misma_url_redireccion",
                                url=redir_final_url,
                                file_size_bytes=size,
                                content_sha256=sha256,
                                verified_at=datetime.now(timezone.utc).isoformat(),
                                metadata={
                                    "source_rung": 1,
                                    "method": "redirect_follow",
                                    "original_url": cand_url,
                                    "redirected_from": cand_url,
                                },
                            )

            # 3. Traducción a dominio sucesor (relocation_manager.translate_url_to_successor)
            if hasattr(self, "relocation_manager"):
                try:
                    for succ_u in self.relocation_manager.translate_url_to_successor(cand_url):
                        if self.is_url_in_inventory(portal, succ_u) or self.is_url_already_recovered(succ_u):
                            continue
                        if self._check_head(succ_u, require_document_type=True):
                            res_succ = self.fetch_and_verify(succ_u)
                            if res_succ:
                                size, sha256 = res_succ
                                sample = getattr(self, "_last_download_sample", b"")
                                if sample and not self._verify_institution_content(portal, sample):
                                    continue
                                ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, succ_u, sha256, 1)
                                if ok_qg:
                                    return RecoveredPeriod(
                                        portal=portal,
                                        dataset_id=dataset_id,
                                        period=period,
                                        recovery_rung=RecoveryRung.RUNG_1_KNOWN_URL,
                                        rung_name="misma_url_reubicada",
                                        url=succ_u,
                                        file_size_bytes=size,
                                        content_sha256=sha256,
                                        verified_at=datetime.now(timezone.utc).isoformat(),
                                        metadata={
                                            "source_rung": 1,
                                            "method": "known_url_successor_mapping",
                                            "original_url": cand_url,
                                        },
                                    )
                except Exception as e:
                    logger.debug("Error probando sucesor para %s: %s", cand_url, e)

            # 4. Si está ELIMINADA (404/410), consultar el directorio superior
            # Solo aplica si cand_url no está en inventario
            if not self.is_url_in_inventory(portal, cand_url):
                parsed = urlparse(cand_url)
                path_parts = [p for p in parsed.path.split("/") if p]
                if path_parts:
                    parent_path = "/" + "/".join(path_parts[:-1]) + "/"
                    parent_url = urlunparse((parsed.scheme, parsed.netloc, parent_path, "", "", ""))
                    try:
                        dir_resp = self.fetcher.session.get(parent_url, timeout=self.timeout)
                        if dir_resp.status_code == 200 and "text/html" in dir_resp.headers.get("Content-Type", ""):
                            links = re.findall(r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\']', dir_resp.text, re.I)
                            doc_exts = (".pdf", ".xlsx", ".xls", ".zip", ".csv")
                            year_str = period[:4]
                            for href in links:
                                href_lower = href.lower()
                                if any(href_lower.endswith(ext) for ext in doc_exts) and year_str in href_lower:
                                    resolved_url = urljoin(parent_url, href)
                                    if self.is_url_in_inventory(portal, resolved_url) or self.is_url_already_recovered(resolved_url):
                                        continue
                                    res = self.fetch_and_verify(resolved_url)
                                    if res:
                                        size, sha256 = res
                                        ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, resolved_url, sha256, 1)
                                        if ok_qg:
                                            return RecoveredPeriod(
                                                portal=portal,
                                                dataset_id=dataset_id,
                                                period=period,
                                                recovery_rung=RecoveryRung.RUNG_1_KNOWN_URL,
                                                rung_name="directorio_superior",
                                                url=resolved_url,
                                                file_size_bytes=size,
                                                content_sha256=sha256,
                                                verified_at=datetime.now(timezone.utc).isoformat(),
                                                metadata={"source_rung": 1, "method": "parent_directory_listing", "original_url": cand_url},
                                            )
                    except Exception as e:
                        logger.debug("Error consultando directorio superior %s: %s", parent_url, e)

            # 5. Probar variantes deterministas de la misma URL (codificación, separadores, capitalización)
            # Solo aplica si cand_url no está en inventario
            if not self.is_url_in_inventory(portal, cand_url):
                variants = self._generate_url_variants(cand_url)
                for var_url in variants:
                    if var_url == cand_url or self.is_url_in_inventory(portal, var_url) or self.is_url_already_recovered(var_url):
                        continue
                    res = self.fetch_and_verify(var_url)
                    if res:
                        size, sha256 = res
                        ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, var_url, sha256, 1)
                        if ok_qg:
                            return RecoveredPeriod(
                                portal=portal,
                                dataset_id=dataset_id,
                                period=period,
                                recovery_rung=RecoveryRung.RUNG_1_KNOWN_URL,
                                rung_name="variante_url_conocida",
                                url=var_url,
                                file_size_bytes=size,
                                content_sha256=sha256,
                                verified_at=datetime.now(timezone.utc).isoformat(),
                                metadata={"source_rung": 1, "method": "url_variant", "original_url": cand_url},
                            )

        return None



    def _build_template_urls(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> List[str]:
        """Construye las URLs candidatas basadas en plantillas de serie conocidas."""
        templates = self.SERIES_TEMPLATES.get((portal, dataset_id), [])
        if not templates:
            return []

        year = int(period[:4])
        yy = f"{year % 100:02d}"
        candidate_urls: List[str] = []

        if periodicity == "semestral":
            sem = period[-1] if "S" in period else "1"
            mon = "jun" if sem == "1" else "dic"
            mon_mayus = "JUN" if sem == "1" else "DIC"
            mes_nombre = "Junio" if sem == "1" else "Diciembre"

            for tmpl in templates:
                try:
                    u = tmpl.format(
                        mon=mon,
                        mon_mayus=mon_mayus,
                        mes_nombre=mes_nombre,
                        yy=yy,
                        yyyy=year,
                        year=year,
                    )
                    candidate_urls.append(u)
                except Exception:
                    pass

        elif periodicity == "mensual":
            m = int(period[5:7]) if len(period) >= 7 else 1
            mes_nombre, mes_min, mes_mayus, mon = self.MONTH_NAMES_ES.get(m, ("Enero", "enero", "ENE", "ene"))
            yyyymm = f"{year}{m:02d}"

            for tmpl in templates:
                try:
                    u = tmpl.format(
                        mon=mon,
                        mes_nombre=mes_nombre,
                        mes_mayus=mes_mayus,
                        yy=yy,
                        yyyy=year,
                        year=year,
                        month=m,
                        yyyymm=yyyymm,
                    )
                    candidate_urls.append(u)
                except Exception:
                    pass
        else:
            for tmpl in templates:
                try:
                    u = tmpl.format(
                        yy=yy,
                        yyyy=year,
                        year=year,
                    )
                    candidate_urls.append(u)
                except Exception:
                    pass

        return candidate_urls

    def _try_rung_2_series_template(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 2: Plantilla de la serie extrapolada con el período faltante (D-17 + HEAD).
        """
        candidate_urls = self._build_template_urls(portal, dataset_id, period, periodicity)
        if not candidate_urls:
            return None

        # Validar candidatos con HEAD primero, luego descargar y verificar bytes y hash
        for url in candidate_urls:
            if self._check_head(url):
                res = self.fetch_and_verify(url)
                if res:
                    size, sha256 = res
                    ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, url, sha256, 2)
                    if not ok_qg:
                        continue
                    return RecoveredPeriod(
                        portal=portal,
                        dataset_id=dataset_id,
                        period=period,
                        recovery_rung=RecoveryRung.RUNG_2_SERIES_TEMPLATE,
                        rung_name="plantilla_serie",
                        url=url,
                        file_size_bytes=size,
                        content_sha256=sha256,
                        verified_at=datetime.now(timezone.utc).isoformat(),
                        metadata={"source_rung": 2, "method": "series_template_d17"},
                    )

        return None

    def _get_sitemap_urls(self, portal: str, dataset_id: str, period: str) -> List[str]:
        """
        Consulta sitemap.xml del portal y devuelve URLs documentales que coincidan
        con el dataset y período buscado.
        """
        if not hasattr(self, "_sitemap_cache"):
            self._sitemap_cache = {}
        cache_key = (portal.lower(), dataset_id, period[:4])
        if cache_key in self._sitemap_cache:
            return self._sitemap_cache[cache_key]

        sitemap_urls: List[str] = []
        endpoints = [
            f"https://www.{portal}.gob.bo/sitemap.xml",
            f"https://{portal}.gob.bo/sitemap.xml",
        ]
        if portal == "bcb":
            endpoints.append("https://www.bcb.gob.bo/sitemap_index.xml")

        year_str = period[:4]
        ds_keywords = [w.lower() for w in re.split(r"[_\W]+", dataset_id) if len(w) >= 3]

        for ep in endpoints:
            try:
                resp = self.fetcher.session.get(ep, timeout=5)
                if resp.status_code == 200 and ("xml" in resp.headers.get("Content-Type", "") or "<urlset" in resp.text or "<sitemapindex" in resp.text):
                    locs = re.findall(r"<loc>(https?://[^<]+)</loc>", resp.text, re.I)
                    for loc in locs:
                        loc_lower = loc.lower()
                        if year_str in loc_lower and any(kw in loc_lower for kw in ds_keywords):
                            if loc not in sitemap_urls:
                                sitemap_urls.append(loc)
                    if sitemap_urls:
                        break
            except Exception as e:
                logger.debug("Error consultando sitemap %s: %s", ep, e)

        self._sitemap_cache[cache_key] = sitemap_urls
        return sitemap_urls

    def _derive_candidates_from_dataset_urls(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> List[str]:
        """
        Escalón 3 (B-62 / P-3): Deriva candidatos a partir de las URLs observadas
        en inventory.db para el propio dataset, infiriendo la parte que varía con
        el período y buscando además en sitemap.xml si el portal lo publica.
        """
        target_year = period[:4]
        try:
            target_yy = f"{int(target_year) % 100:02d}"
        except Exception:
            target_yy = ""

        observed_urls: List[str] = []
        db_path = self.base_output_dir / portal / "inventory.db"
        if db_path.exists():
            try:
                conn = sqlite3.connect(db_path)
                try:
                    cursor = conn.cursor()
                    rows = cursor.execute(
                        "SELECT canonical_url FROM resource_audit_log WHERE dataset_id = ? AND canonical_url LIKE 'http%'",
                        (dataset_id,)
                    ).fetchall()
                    for (u,) in rows:
                        if u and u not in observed_urls:
                            observed_urls.append(u)
                finally:
                    conn.close()
            except Exception as e:
                logger.debug("Error leyendo URLs de dataset %s en inventory: %s", dataset_id, e)

        sitemap_urls = self._get_sitemap_urls(portal, dataset_id, period)
        for sm_u in sitemap_urls:
            if sm_u not in observed_urls:
                observed_urls.append(sm_u)

        if not observed_urls:
            return []

        q_map = {
            1: {"full": "primer trimestre", "short": "primer", "ord": "1er", "tok": "Q1"},
            2: {"full": "segundo trimestre", "short": "segundo", "ord": "2do", "tok": "Q2"},
            3: {"full": "tercer trimestre", "short": "tercer", "ord": "3er", "tok": "Q3"},
            4: {"full": "cuarto trimestre", "short": "cuarto", "ord": "4to", "tok": "Q4"},
        }
        sem_map = {
            1: {"full": "primer semestre", "short": "primer", "mon": "jun", "ord": "1er", "tok": "S1"},
            2: {"full": "segundo semestre", "short": "segundo", "mon": "dic", "ord": "2do", "tok": "S2"},
        }
        mes_map = {
            1: ("enero", "ene", "01"), 2: ("febrero", "feb", "02"), 3: ("marzo", "mar", "03"),
            4: ("abril", "abr", "04"), 5: ("mayo", "may", "05"), 6: ("junio", "jun", "06"),
            7: ("julio", "jul", "07"), 8: ("agosto", "ago", "08"), 9: ("septiembre", "sep", "09"),
            10: ("octubre", "oct", "10"), 11: ("noviembre", "nov", "11"), 12: ("diciembre", "dic", "12"),
        }

        derived_candidates: List[str] = []

        for raw_u in observed_urls:
            unquoted_u = unquote(raw_u)
            src_years = set(re.findall(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", unquoted_u))
            if not src_years:
                src_years = set(re.findall(r"(?<!\d)(\d{2})(?!\d)", unquoted_u))

            if periodicity == "trimestral":
                target_q = None
                if "-Q" in period:
                    try:
                        target_q = int(period.split("-Q")[-1])
                    except Exception:
                        pass
                if not target_q or target_q not in q_map:
                    target_q = 1

                t_info = q_map[target_q]
                all_q_words = ["primer", "primero", "segundo", "tercer", "tercero", "cuarto", "Cuarto", "1er", "2do", "3er", "4to"]

                for sy in src_years:
                    u_replaced_year = re.sub(rf"(?<!\d){re.escape(sy)}(?!\d)", target_year, unquoted_u)
                    for qw in all_q_words:
                        if re.search(rf"\b{re.escape(qw)}\b", u_replaced_year, re.I):
                            cand1 = re.sub(rf"\b{re.escape(qw)}\b", t_info["short"], u_replaced_year, flags=re.I)
                            cand2 = re.sub(rf"\b{re.escape(qw)}\b", t_info["ord"], u_replaced_year, flags=re.I)
                            for c in (cand1, cand2):
                                for fin_cand in (c, c.replace(" ", "%20")):
                                    if fin_cand not in derived_candidates:
                                        derived_candidates.append(fin_cand)

                    for q_num in (1, 2, 3, 4):
                        tok = f"Q{q_num}"
                        if tok in u_replaced_year or tok.lower() in u_replaced_year.lower():
                            cand = re.sub(rf"\b{tok}\b", t_info["tok"], u_replaced_year, flags=re.I)
                            for fin_cand in (cand, cand.replace(" ", "%20")):
                                if fin_cand not in derived_candidates:
                                    derived_candidates.append(fin_cand)

            elif periodicity == "semestral":
                target_s = 2 if period.endswith("S2") or period.endswith("2") else 1
                s_info = sem_map[target_s]
                all_sem_words = ["primer", "segundo", "1er", "2do"]
                all_months = ["jun", "junio", "dic", "diciembre"]

                for sy in src_years:
                    # Si sy es de 2 dígitos, reemplazar por target_yy o target_year
                    sub_y = target_yy if len(sy) == 2 and target_yy else target_year
                    u_replaced_year = re.sub(rf"(?<!\d){re.escape(sy)}(?!\d)", sub_y, unquoted_u)
                    u_replaced_4y = re.sub(rf"(?<!\d){re.escape(sy)}(?!\d)", target_year, unquoted_u)

                    for u_base in (u_replaced_year, u_replaced_4y):
                        for sw in all_sem_words:
                            if re.search(rf"\b{re.escape(sw)}\b", u_base, re.I):
                                cand = re.sub(rf"\b{re.escape(sw)}\b", s_info["short"], u_base, flags=re.I)
                                for fin_cand in (cand, cand.replace(" ", "%20")):
                                    if fin_cand not in derived_candidates:
                                        derived_candidates.append(fin_cand)
                        for mw in all_months:
                            pattern_m = rf"(?<![a-zA-Z]){re.escape(mw)}(?![a-zA-Z])"
                            if re.search(pattern_m, u_base, re.I):
                                cand = re.sub(pattern_m, s_info["mon"], u_base, flags=re.I)
                                for fin_cand in (cand, cand.replace(" ", "%20")):
                                    if fin_cand not in derived_candidates:
                                        derived_candidates.append(fin_cand)
                        for s_num in (1, 2):
                            tok = f"S{s_num}"
                            if tok in u_base or tok.lower() in u_base.lower():
                                cand = re.sub(rf"\b{tok}\b", s_info["tok"], u_base, flags=re.I)
                                for fin_cand in (cand, cand.replace(" ", "%20")):
                                    if fin_cand not in derived_candidates:
                                        derived_candidates.append(fin_cand)

            elif periodicity == "mensual":
                try:
                    m_num = int(period.split("-")[1])
                except Exception:
                    m_num = 1
                m_full, m_short, m_two = mes_map.get(m_num, ("enero", "ene", "01"))

                for sy in src_years:
                    sub_y = target_yy if len(sy) == 2 and target_yy else target_year
                    u_replaced_year = re.sub(rf"(?<!\d){re.escape(sy)}(?!\d)", sub_y, unquoted_u)
                    for num, (f_name, s_name, t_dig) in mes_map.items():
                        pat_full = rf"(?<![a-zA-Z]){re.escape(f_name)}(?![a-zA-Z])"
                        if re.search(pat_full, u_replaced_year, re.I):
                            cand = re.sub(pat_full, m_full, u_replaced_year, flags=re.I)
                            for fin_cand in (cand, cand.replace(" ", "%20")):
                                if fin_cand not in derived_candidates:
                                    derived_candidates.append(fin_cand)
                        pat_short = rf"(?<![a-zA-Z]){re.escape(s_name)}(?![a-zA-Z])"
                        if re.search(pat_short, u_replaced_year, re.I):
                            cand = re.sub(pat_short, m_short, u_replaced_year, flags=re.I)
                            for fin_cand in (cand, cand.replace(" ", "%20")):
                                if fin_cand not in derived_candidates:
                                    derived_candidates.append(fin_cand)
                        if re.search(rf"(?:_|-){t_dig}(?:\.|\b)", u_replaced_year):
                            cand = re.sub(rf"(?<=_|-){t_dig}(?=\.|\b)", m_two, u_replaced_year)
                            for fin_cand in (cand, cand.replace(" ", "%20")):
                                if fin_cand not in derived_candidates:
                                    derived_candidates.append(fin_cand)

            else:
                for sy in src_years:
                    cand = re.sub(rf"(?<!\d){re.escape(sy)}(?!\d)", target_year, unquoted_u)
                    for fin_cand in (cand, cand.replace(" ", "%20")):
                        if fin_cand not in derived_candidates:
                            derived_candidates.append(fin_cand)

        return derived_candidates

    def _try_rung_3_same_domain_alternate(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 3: Otra ruta dentro del mismo dominio (variaciones sintácticas y derivación de serie).
        Deriva candidatos de las URLs observadas del propio dataset (inventory.db y sitemap.xml)
        reemplazando año y período, complementado con variaciones sintácticas de ruta (B-62 / P-3).
        """
        candidate_urls = self._derive_candidates_from_dataset_urls(portal, dataset_id, period, periodicity)

        template_seeds = self._build_template_urls(portal, dataset_id, period, periodicity)
        if hasattr(self, "relocation_manager"):
            for s_url in template_seeds:
                for var_u in self.relocation_manager.generate_path_variants(s_url, period=period):
                    if var_u not in candidate_urls:
                        candidate_urls.append(var_u)

        for url in candidate_urls:
            if self.is_url_in_inventory(portal, url) or self.is_url_already_recovered(url):
                continue
            if self._check_head(url):
                res = self.fetch_and_verify(url)
                if res:
                    size, sha256 = res
                    sample = getattr(self, "_last_download_sample", b"")
                    if sample and not self._verify_institution_content(portal, sample):
                        continue
                    ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, url, sha256, 3)
                    if not ok_qg:
                        continue
                    return RecoveredPeriod(
                        portal=portal,
                        dataset_id=dataset_id,
                        period=period,
                        recovery_rung=RecoveryRung.RUNG_3_SAME_DOMAIN_ALTERNATE,
                        rung_name="ruta_alterna_dominio",
                        url=url,
                        file_size_bytes=size,
                        content_sha256=sha256,
                        verified_at=datetime.now(timezone.utc).isoformat(),
                        metadata={"source_rung": 3, "method": "same_domain_alternate_path"},
                    )

        return None

    def _get_dataset_cdx_pattern(self, portal: str, dataset_id: str) -> str:
        """Determina el patrón de búsqueda para la API CDX de Wayback Machine a partir de las URLs conocidas del dataset (B-63)."""
        db_path = self.base_output_dir / portal / "inventory.db"
        if db_path.exists():
            try:
                with sqlite3.connect(db_path) as conn:
                    rows = conn.execute(
                        "SELECT canonical_url FROM resource_audit_log WHERE dataset_id = ?",
                        (dataset_id,)
                    ).fetchall()
                    doc_urls = [
                        r[0] for r in rows
                        if r[0] and any(r[0].lower().endswith(ext) for ext in (".pdf", ".xlsx", ".xls", ".zip", ".csv"))
                    ]
                    if not doc_urls and rows:
                        doc_urls = [r[0] for r in rows if r[0]]

                    if doc_urls:
                        from collections import Counter
                        import os
                        domains = Counter(urlparse(u).netloc for u in doc_urls)
                        primary_domain = domains.most_common(1)[0][0]
                        domain_urls = [u for u in doc_urls if urlparse(u).netloc == primary_domain]

                        paths = [urlparse(u).path for u in domain_urls]
                        common_p = os.path.commonprefix(paths)
                        if "/" in common_p:
                            base_dir = common_p.rsplit("/", 1)[0]
                            if base_dir:
                                return f"{primary_domain}{base_dir}/*"
                        return f"{primary_domain}/*"
            except Exception as e:
                logger.debug("Error infiriendo patron CDX desde inventory.db para %s/%s: %s", portal, dataset_id, e)

        # Fallback a semillas de plantillas si existen
        tpls = self.SERIES_TEMPLATES.get((portal, dataset_id), [])
        if tpls:
            p = urlparse(tpls[0])
            path_dir = p.path.rsplit("/", 1)[0]
            return f"{p.netloc}{path_dir}/*"

        # Fallback a dominios autorizados de la fuente
        allowed = self._get_allowed_domains(portal)
        return f"{allowed[0]}/*" if allowed else f"{portal}.gob.bo/*"

    def _get_dataset_cdx_snapshots(self, portal: str, dataset_id: str) -> List[Dict[str, str]]:
        """Obtiene y cachea las instantáneas CDX de Wayback Machine para el dataset dado (B-63)."""
        cache_key = (portal, dataset_id)
        if cache_key in self._cdx_snapshots_cache:
            return self._cdx_snapshots_cache[cache_key]

        pattern = self._get_dataset_cdx_pattern(portal, dataset_id)
        try:
            snapshots = query_cdx_snapshots(pattern, timeout=15, session=self._session)
        except Exception as e:
            logger.warning("Error consultando motor CDX para %s/%s [%s]: %s", portal, dataset_id, pattern, e)
            snapshots = []

        self._cdx_snapshots_cache[cache_key] = snapshots
        return snapshots

    def _snapshot_matches_period(self, snap: Dict[str, str], period: str, periodicity: str) -> bool:
        """Determina si una instantánea CDX corresponde al período faltante especificado (B-63)."""
        target = unquote(snap.get("original", "")).lower()
        year = period[:4]
        yy = f"{int(year) % 100:02d}"

        if periodicity == "anual":
            return bool(re.search(rf"(?<!\d){re.escape(period)}(?!\d)", target))

        if periodicity == "semestral":
            is_s1 = period.endswith("S1") or period.endswith("-1") or period.endswith(" 1")
            s_toks = ["jun", "junio", "primer", "1er", "s1"] if is_s1 else ["dic", "diciembre", "segundo", "2do", "s2"]
            has_year = bool(re.search(rf"(?<!\d)({re.escape(year)}|{re.escape(yy)})(?!\d)", target))
            if not has_year:
                return False
            return any(re.search(rf"(?<![a-zA-Z]){re.escape(tok)}(?![a-zA-Z])", target) for tok in s_toks)

        if periodicity == "trimestral":
            target_q = 1
            if "-Q" in period:
                try:
                    target_q = int(period.split("-Q")[-1])
                except Exception:
                    pass
            q_tok_map = {
                1: ["primer", "1er", "q1", "marzo", "mar"],
                2: ["segundo", "2do", "q2", "junio", "jun"],
                3: ["tercer", "3er", "q3", "septiembre", "sep", "set"],
                4: ["cuarto", "4to", "q4", "diciembre", "dic"],
            }
            q_toks = q_tok_map.get(target_q, ["primer", "1er", "q1"])
            has_year = bool(re.search(rf"(?<!\d)({re.escape(year)}|{re.escape(yy)})(?!\d)", target))
            if not has_year:
                return False
            return any(re.search(rf"(?<![a-zA-Z]){re.escape(tok)}(?![a-zA-Z])", target) for tok in q_toks)

        if periodicity == "mensual":
            try:
                m_num = int(period.split("-")[1])
            except Exception:
                m_num = 1
            meses_map = {
                1: ("enero", "ene", "01"), 2: ("febrero", "feb", "02"), 3: ("marzo", "mar", "03"),
                4: ("abril", "abr", "04"), 5: ("mayo", "may", "05"), 6: ("junio", "jun", "06"),
                7: ("julio", "jul", "07"), 8: ("agosto", "ago", "08"), 9: ("septiembre", "sep", "09"),
                10: ("octubre", "oct", "10"), 11: ("noviembre", "nov", "11"), 12: ("diciembre", "dic", "12"),
            }
            m_full, m_short, m_dig = meses_map.get(m_num, ("enero", "ene", "01"))
            has_year = bool(re.search(rf"(?<!\d)({re.escape(year)}|{re.escape(yy)})(?!\d)", target))
            if not has_year:
                return False
            if f"{year}{m_dig}" in target:
                return True
            return bool(
                re.search(rf"(?<![a-zA-Z])({re.escape(m_full)}|{re.escape(m_short)})(?![a-zA-Z])", target) or
                re.search(rf"(?:_|-){m_dig}(?:\.|\b)", target)
            )

        return bool(re.search(rf"(?<!\d){re.escape(year)}(?!\d)", target))

    def _try_rung_4_wayback_archive(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 4: Archivo histórico de la web (Wayback Machine CDX Engine) (B-63 / P-4).
        Consulta la API CDX de Wayback Machine mediante wayback_engine para el patrón de URLs conocidas
        del dataset (sin condicionales cableados), filtrando por período y validando contra compuertas de calidad.
        """
        snapshots = self._get_dataset_cdx_snapshots(portal, dataset_id)
        cdx_pattern = self._get_dataset_cdx_pattern(portal, dataset_id)

        if snapshots:
            for snap in snapshots:
                if not self._snapshot_matches_period(snap, period, periodicity):
                    continue

                snap_url = snap.get("snapshot_url")
                orig_url = snap.get("original", "")
                if not snap_url:
                    continue

                # Evitar URLs ya presentes en inventario o recuperadas
                if self.is_url_in_inventory(portal, snap_url) or self.is_url_in_inventory(portal, orig_url):
                    continue
                if self.is_url_already_recovered(snap_url) or self.is_url_already_recovered(orig_url):
                    continue

                # Descarga y verificación directa
                res = self.fetch_and_verify(snap_url)
                if not res:
                    continue

                size, sha256 = res
                sample = getattr(self, "_last_download_sample", b"")
                if sample and not self._verify_institution_content(portal, sample):
                    continue

                ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, snap_url, sha256, 4)
                if not ok_qg:
                    continue

                return RecoveredPeriod(
                    portal=portal,
                    dataset_id=dataset_id,
                    period=period,
                    recovery_rung=RecoveryRung.RUNG_4_WAYBACK_ARCHIVE,
                    rung_name="archivo_historico",
                    url=snap_url,
                    file_size_bytes=size,
                    content_sha256=sha256,
                    verified_at=datetime.now(timezone.utc).isoformat(),
                    metadata={
                        "source_rung": 4,
                        "method": "cdx_wayback_engine",
                        "is_historical_archive": True,
                        "archive_source": "wayback_machine",
                        "original_url": orig_url,
                        "archive_timestamp": snap.get("timestamp", ""),
                        "cdx_query": cdx_pattern,
                    },
                )

        # Fallback a Availability API si CDX no indexó la ruta o para retrocompatibilidad
        candidate_urls = self._build_template_urls(portal, dataset_id, period, periodicity)
        for target_url in candidate_urls:
            api = f"https://archive.org/wayback/available?url={quote(target_url, safe=':/?=')}"
            try:
                resp = self._session.get(api, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    snap_data = data.get("archived_snapshots", {}) if isinstance(data, dict) else {}
                    closest = snap_data.get("closest", {})
                    if closest.get("available") and str(closest.get("status")) == "200":
                        snap_url = closest.get("url")
                        res = self.fetch_and_verify(snap_url)
                        if res:
                            size, sha256 = res
                            sample = getattr(self, "_last_download_sample", b"")
                            if sample and not self._verify_institution_content(portal, sample):
                                continue
                            ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, snap_url, sha256, 4)
                            if not ok_qg:
                                continue
                            return RecoveredPeriod(
                                portal=portal,
                                dataset_id=dataset_id,
                                period=period,
                                recovery_rung=RecoveryRung.RUNG_4_WAYBACK_ARCHIVE,
                                rung_name="archivo_historico",
                                url=snap_url,
                                file_size_bytes=size,
                                content_sha256=sha256,
                                verified_at=datetime.now(timezone.utc).isoformat(),
                                metadata={
                                    "source_rung": 4,
                                    "method": "wayback_archive_snapshot",
                                    "is_historical_archive": True,
                                    "target_url": target_url,
                                },
                            )
            except Exception as e:
                logger.debug("Error consultando Availability API para %s: %s", target_url, e)

        return None

    def _get_allowed_domains(self, portal: str) -> List[str]:
        """Obtiene la lista de dominios permitidos para el portal desde su configuración YAML."""
        cfg_path = self.base_config_dir / f"source_{portal}.yaml"
        if cfg_path.exists():
            try:
                import yaml
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    domains = data.get("source", {}).get("allowed_domains", [])
                    if domains:
                        base_domains = [d.strip().lower() for d in domains if d and isinstance(d, str)]
            except Exception as e:
                logger.debug("Error leyendo allowed_domains de %s: %s", cfg_path, e)
                base_domains = []
        else:
            base_domains = []

        if not base_domains:
            fallbacks = {
                "bcb": ["bcb.gob.bo", "www.bcb.gob.bo", "deudaexternapublica.bcb.gob.bo"],
                "asfi": ["asfi.gob.bo", "www.asfi.gob.bo"],
                "ine": ["ine.gob.bo", "www.ine.gob.bo"],
            }
            base_domains = fallbacks.get(portal.lower(), [f"{portal}.gob.bo"])

        # P-6 / D-18: Solo dominios base autorizados del portal (sucesores van a cola de herencia)
        return sorted(list(set(base_domains)))

    def _verify_institution_content(self, portal: str, content: bytes) -> bool:
        """
        D-01 & H-4: Verifica que el contenido descargado mencione palabras clave de la institución real.
        Usa fronteras de palabra (\\b) para evitar falsos positivos con subcadenas como 'ine' en 'linea'.
        Rechaza si el contenido es meramente una página HTML.
        """
        if not content:
            return False

        head_sample = content[:1024].lstrip().lower()
        if head_sample.startswith(b"<!doctype html") or head_sample.startswith(b"<html"):
            return False

        sample = content[:131072].decode("latin-1", errors="ignore").lower()
        normalized = unicodedata.normalize("NFKD", sample)
        clean_text = "".join(c for c in normalized if not unicodedata.combining(c))

        portal_regexes = {
            "bcb": [r"\bbanco central de bolivia\b", r"\bbcb\b"],
            "asfi": [r"\bautoridad de supervision del sistema financiero\b", r"\basfi\b"],
            "ine": [r"\binstituto nacional de estadistica\b", r"\bine\b"],
        }
        regexes = list(portal_regexes.get(portal.lower(), [rf"\b{re.escape(portal.lower())}\b"]))

        # También admitir palabras clave de entidades sucesoras o predecesoras autorizadas
        p_clean = portal.lower().replace("-", "_")
        for key, succ_info in CANONICAL_SUCCESSIONS.items():
            if key == p_clean or portal.lower() in key:
                for succ in succ_info.get("successors", []):
                    for kw in succ.get("keywords", []):
                        regexes.append(rf"\b{re.escape(kw.lower())}\b")

        return any(re.search(rx, clean_text) for rx in regexes)

    def _verify_period_correspondence(
        self, period: str, periodicity: str, url: str, content: bytes
    ) -> bool:
        """
        H-3: Comprueba que el candidato (URL o contenido descargado) corresponda
        efectivamente al período buscado, impidiendo admisiones espurias de índices.
        """
        p_clean = period.strip().upper()
        url_lower = url.lower()

        sample_text = ""
        if content:
            sample_text = content[:131072].decode("latin-1", errors="ignore").lower()
            sample_text = "".join(c for c in unicodedata.normalize("NFKD", sample_text) if not unicodedata.combining(c))

        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", p_clean)
        if not year_match:
            return True
        target_year = year_match.group(1)
        year_pattern = rf"(?<!\d)(?:{target_year}|{target_year[-2:]})(?!\d)"
        in_url_year = bool(re.search(year_pattern, url_lower))
        in_content_year = bool(re.search(year_pattern, sample_text))

        if not (in_url_year or in_content_year):
            return False

        if "-S" in p_clean:
            sem_num = p_clean.split("-S")[-1]
            if sem_num == "1":
                sem_terms = [r"\bs1\b", r"\b1sem\b", r"\bsem1\b", r"\bjunio\b", r"(?<![a-z])jun(?![a-z])", r"\bprimer semestre\b", r"\bi semestre\b"]
            else:
                sem_terms = [r"\bs2\b", r"\b2sem\b", r"\bsem2\b", r"\bdiciembre\b", r"(?<![a-z])dic(?![a-z])", r"\bsegundo semestre\b", r"\bii semestre\b"]
            in_url_sem = any(re.search(t, url_lower) for t in sem_terms)
            in_content_sem = any(re.search(t, sample_text) for t in sem_terms)
            return in_url_sem or in_content_sem

        month_match = re.match(r"^\d{4}-(\d{2})$", p_clean)
        if month_match:
            mm = month_match.group(1)
            month_names = {
                "01": ["enero", "ene", "01"],
                "02": ["febrero", "feb", "02"],
                "03": ["marzo", "mar", "03"],
                "04": ["abril", "abr", "04"],
                "05": ["mayo", "may", "05"],
                "06": ["junio", "jun", "06"],
                "07": ["julio", "jul", "07"],
                "08": ["agosto", "ago", "08"],
                "09": ["septiembre", "sep", "set", "09"],
                "10": ["octubre", "oct", "10"],
                "11": ["noviembre", "nov", "11"],
                "12": ["diciembre", "dic", "12"],
            }
            terms = [rf"\b{t}\b" for t in month_names.get(mm, [mm])]
            in_url_m = any(re.search(t, url_lower) for t in terms)
            in_content_m = any(re.search(t, sample_text) for t in terms)
            return in_url_m or in_content_m

        return True

    def save_inheritance_candidates(self, output_path: str = "docs/entregas/cola_herencia_b55.json"):
        """Persiste los candidatos de dominios externos propuestos por el agente para la cola de herencia de B-55 (O-1)."""
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        out = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_candidates": len(self.inheritance_candidates),
            "candidates": self.inheritance_candidates,
        }
        p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Cola de herencia para B-55 persistida en: %s (%d candidatos)", p, len(self.inheritance_candidates))

    def _ask_gemini_for_candidates(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> List[str]:
        """
        Escalón 5: Consulta a Gemini para obtener URLs candidatas de períodos faltantes.
        Respeta el límite estricto de llamadas por corrida (max_gemini_calls / D-08).
        """
        if self.gemini_calls_count >= self.max_gemini_calls:
            logger.info(
                "Tope de llamadas a Gemini alcanzado (%d/%d), no se consulta para %s/%s/%s",
                self.gemini_calls_count,
                self.max_gemini_calls,
                portal,
                dataset_id,
                period,
            )
            return []

        if not getattr(self.fetcher, "gemini_api_key", None):
            return []

        prompt = (
            f"Eres un asistente de recuperación documental para portales públicos de Bolivia. "
            f"Institución: {portal.upper()}, Dataset: {dataset_id}, Período faltante: {period} (periodicidad {periodicity}). "
            f"Indica hasta 5 URLs directas de documentos (PDF, XLSX, ZIP) o páginas de descarga donde este período "
            f"podría encontrarse dentro del portal oficial o sus subdominios. "
            f"Responde estrictamente con un JSON array de strings con las URLs candidatas, sin explicaciones ni bloques de texto adicional."
        )

        try:
            self.gemini_calls_count += 1
            text = self.fetcher._generate_gemini_content(prompt)
            if not text:
                return []
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                cleaned = cleaned.rstrip("`").strip()
            data = json.loads(cleaned)
            if isinstance(data, list):
                return [str(u).strip() for u in data if isinstance(u, str) and u.startswith("http")]
            return []
        except Exception as e:
            logger.warning("Error consultando Gemini para período %s/%s/%s: %s", portal, dataset_id, period, e)
            return []

    def _try_rung_5_agent_gemini(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 5: El agente (Gemini) propone candidatos cuando los cuatro escalones deterministas fallaron.
        Reglas estrictas de guardarraíl (docs/arquitectura_integracion.md §6):
        1. El agente propone, no admite directamente en inventory.db.
        2. Toda propuesta pasa por HTTP HEAD (status 200, Content-Length > 0 y tipo documental D-17).
        3. Toda propuesta pasa por verificación de contenido institucional (D-01 / H-4).
        4. Cambio de dominio institucional nunca es automático (se encola para herencia B-55 con evidencia / O-1).
        5. Límite de llamadas acotado y registrado por corrida (max_gemini_calls / D-08).
        6. Queda registrado en el registro que provino del escalón 5 (agente_gemini).
        """
        candidates = self._ask_gemini_for_candidates(portal, dataset_id, period, periodicity)
        if not candidates:
            return None

        allowed_domains = self._get_allowed_domains(portal)

        for cand_url in candidates:
            # Regla 4 & O-1: Dominio permitido o encolar para B-55
            domain = urlparse(cand_url).netloc.lower()
            if ":" in domain:
                domain = domain.split(":")[0]

            is_base = any(domain == ad or domain.endswith("." + ad) for ad in allowed_domains)

            if not is_base:
                is_succ = hasattr(self, "relocation_manager") and (
                    self.relocation_manager.is_authorized_successor(portal, domain)
                    or any(self.relocation_manager.is_authorized_successor(ad, domain) for ad in allowed_domains)
                )
                reason = (
                    "Dominio sucesor derivado a cola de herencia B-55 (D-18 / P-6)"
                    if is_succ
                    else "Dominio externo sugerido por LLM (cola de herencia B-55)"
                )
                logger.info(
                    "Candidato del agente derivado a cola de herencia B-55 (%s no en %s): %s",
                    domain,
                    allowed_domains,
                    cand_url,
                )
                self.inheritance_candidates.append({
                    "portal": portal,
                    "dataset_id": dataset_id,
                    "period": period,
                    "proposed_url": cand_url,
                    "proposed_domain": domain,
                    "allowed_domains": allowed_domains,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "reason": reason,
                    "is_successor": is_succ,
                })
                continue

            # Regla 2: HEAD status 200, tamaño > 0 Y TIPO DOCUMENTAL (D-17 / H-2)
            if not self._check_head(cand_url, require_document_type=True):
                continue

            # Descargar y calcular bytes y SHA-256 (rechaza text/html en streaming / H-1)
            res = self.fetch_and_verify(cand_url)
            if not res:
                continue
            size, sha256 = res

            # Regla 3: Verificación de contenido institucional reforzada (D-01 / H-4)
            sample = getattr(self, "_last_download_sample", b"")
            if not self._verify_institution_content(portal, sample):
                logger.info("Candidato del agente descartado por fallar verificación de contenido (D-01): %s", cand_url)
                continue

            # Regla H-3: Verificación de correspondencia con el período pedido
            if not self._verify_period_correspondence(period, periodicity, cand_url, sample):
                logger.info("Candidato descartado por no corresponder al período %s: %s", period, cand_url)
                continue

            # Regla H-3 & O-1: No admitir documentos que ya estén en inventory.db ni repetidos en la corrida
            if self.is_url_in_inventory(portal, cand_url) or self.is_url_already_recovered(cand_url):
                continue

            # Compuertas de calidad Fase 5 (B-59)
            ok_qg, _ = self._check_quality_gates(portal, dataset_id, period, cand_url, sha256, 5)
            if not ok_qg:
                continue

            self._recovered_urls.add(cand_url)
            return RecoveredPeriod(
                portal=portal,
                dataset_id=dataset_id,
                period=period,
                recovery_rung=RecoveryRung.RUNG_5_AGENT_GEMINI,
                rung_name="agente_gemini",
                url=cand_url,
                file_size_bytes=size,
                content_sha256=sha256,
                verified_at=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "source_rung": 5,
                    "method": "gemini_agent_helper",
                    "domain_verified": domain,
                },
            )

        return None

    def recover_period(
        self, portal: str, dataset_id: str, period: str, periodicity: str = "anual"
    ) -> Optional[RecoveredPeriod]:
        """
        Busca un período faltante a través de los cinco escalones en orden estricto de menor a mayor riesgo.
        Se detiene en el primer escalón que tenga éxito.
        Verifica en todos los escalones que la URL recuperada no exista previamente en el inventario (O-1).
        """
        for rung_fn in (
            self._try_rung_1_known_url,
            self._try_rung_2_series_template,
            self._try_rung_3_same_domain_alternate,
            self._try_rung_4_wayback_archive,
            self._try_rung_5_agent_gemini,
        ):
            res = rung_fn(portal, dataset_id, period, periodicity)
            if res:
                if self.is_url_in_inventory(portal, res.url):
                    logger.debug("Candidato %s descartado: ya existe en inventory.db", res.url)
                    continue
                if self.is_url_already_recovered(res.url):
                    logger.debug("Candidato %s descartado: ya recuperado en la corrida actual", res.url)
                    continue
                self._recovered_urls.add(res.url)
                return res

        return None

    def recover_missing_periods(
        self, sources: Optional[List[str]] = None, max_recoveries: int = 15
    ) -> List[RecoveredPeriod]:
        """
        Ejecuta la recuperación sistemática de los períodos faltantes detectados en B-53.
        """
        sources = sources or ["bcb", "ine", "asfi"]
        all_recovered: List[RecoveredPeriod] = []

        for src in sources:
            db_path = self.base_output_dir / src / "inventory.db"
            cfg_path = self.base_config_dir / f"source_{src}.yaml"
            if not db_path.exists() or not cfg_path.exists():
                continue

            adapter = GenericSourceAdapter(cfg_path)
            detector = GapDetector(db_path=db_path)

            for rule in adapter.dataset_rules:
                ds_id = rule.get("id")
                periodicity = rule.get("periodicity", "anual")
                tolerance = rule.get("tolerance", 1)

                if periodicity == "eventual":
                    continue

                rep = detector.evaluate_dataset(ds_id, periodicity=periodicity, tolerance=tolerance)
                if not rep.intermediate_gaps:
                    continue

                for gap in reversed(rep.intermediate_gaps):
                    if len(all_recovered) >= max_recoveries:
                        break

                    recovered_item = self.recover_period(
                        portal=src,
                        dataset_id=ds_id,
                        period=gap,
                        periodicity=periodicity,
                    )
                    if recovered_item:
                        all_recovered.append(recovered_item)

                if len(all_recovered) >= max_recoveries:
                    break

            detector.close()
            if len(all_recovered) >= max_recoveries:
                break

        if self.inheritance_candidates:
            self.save_inheritance_candidates()

        return all_recovered

    def dry_run_candidates(
        self, sources: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Dict[str, List[str]]]]:
        """
        Modo dry-run (B-62 / P-3): Lista los candidatos generados/derivados para
        cada período faltante en los datasets con huecos detectados, sin realizar
        descargas ni consumir presupuestos de red/LLM.
        """
        sources = sources or ["bcb", "ine", "asfi"]
        results: Dict[str, Dict[str, Dict[str, List[str]]]] = {}

        for src in sources:
            db_path = self.base_output_dir / src / "inventory.db"
            cfg_path = self.base_config_dir / f"source_{src}.yaml"
            if not db_path.exists() or not cfg_path.exists():
                continue

            adapter = GenericSourceAdapter(cfg_path)
            detector = GapDetector(db_path=db_path)
            results[src] = {}

            for rule in adapter.dataset_rules:
                ds_id = rule.get("id")
                periodicity = rule.get("periodicity", "anual")
                tolerance = rule.get("tolerance", 1)

                if periodicity == "eventual":
                    continue

                rep = detector.evaluate_dataset(ds_id, periodicity=periodicity, tolerance=tolerance)
                if not rep.intermediate_gaps:
                    continue

                results[src][ds_id] = {}

                # Escalón 4: Consulta CDX al motor de Wayback (B-63)
                cdx_pat = self._get_dataset_cdx_pattern(src, ds_id)
                cdx_snaps = self._get_dataset_cdx_snapshots(src, ds_id)
                self.dry_run_cdx_queries[(src, ds_id)] = (cdx_pat, len(cdx_snaps))

                for gap in rep.intermediate_gaps:
                    cands = self._derive_candidates_from_dataset_urls(
                        portal=src,
                        dataset_id=ds_id,
                        period=gap,
                        periodicity=periodicity,
                    )
                    for t_url in self._build_template_urls(src, ds_id, gap, periodicity):
                        if t_url not in cands:
                            cands.append(t_url)

                    # Candidatos derivados de instantáneas CDX (Escalón 4)
                    for snap in cdx_snaps:
                        if self._snapshot_matches_period(snap, gap, periodicity):
                            snap_u = snap.get("snapshot_url")
                            if snap_u and snap_u not in cands:
                                cands.append(snap_u)

                    results[src][ds_id][gap] = cands

            detector.close()

        return results
