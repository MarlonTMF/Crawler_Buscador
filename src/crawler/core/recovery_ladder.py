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
from urllib.parse import quote, unquote, urlparse

import requests
import urllib3

from crawler.core.fetcher import HttpFetcher
from crawler.core.gap_detector import GapDetector
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
        self._recovered_urls: Set[str] = set()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": getattr(self.fetcher, "user_agent", "DataX-Prospector/1.0 (+http://datax.org)")
        })

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

    def _try_rung_1_known_url(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 1: Buscar la misma URL conocida anteriormente en el catálogo / historial.
        NOTA ESTRUCTURAL: Si los candidatos se obtienen de resource_audit_log de inventory.db
        y luego se descartan mediante is_url_in_inventory (O-1), este escalón resulta inerte
        para documentos ya cosechados. Su propósito funcional pleno requerirá una tabla de URLs
        históricas o previamente fallidas no indexadas.
        """
        db_path = self.base_output_dir / portal / "inventory.db"
        if not db_path.exists():
            return None

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Extraer año y subperíodo
        year_str = period[:4]
        sub_period = period[5:] if len(period) > 4 else ""

        # Palabras clave según periodicidad
        keywords = [year_str]
        if periodicity == "semestral":
            if sub_period == "S2":
                keywords.extend(["final", "segundo_semestre", "2do_semestre", "cierre", "segundo"])
            elif sub_period == "S1":
                keywords.extend(["inicial", "primer_semestre", "1er_semestre", "apertura", "primer"])
        elif periodicity == "trimestral":
            tri_map = {"Q1": "primer", "Q2": "segundo", "Q3": "tercer", "Q4": "cuarto"}
            if sub_period in tri_map:
                keywords.append(tri_map[sub_period])

        candidate_urls: List[str] = []
        try:
            rows = cursor.execute(
                "SELECT canonical_url FROM resource_audit_log WHERE dataset_id = ?",
                (dataset_id,)
            ).fetchall()

            for (url,) in rows:
                if not url or not url.startswith("http"):
                    continue
                lower_url = unquote(url).lower()
                # O-3: Descartar si el año aparece como parte de un rango (ej: 1988-2016)
                if re.search(r"\b\d{4}\s*[-_al/]+\s*\d{4}\b", lower_url):
                    continue
                # Coincidencia con límite de palabra / no dígito adyacente
                if re.search(rf"(?<!\d){re.escape(year_str)}(?!\d)", lower_url):
                    if len(keywords) > 1:
                        # Verificar si contiene alguna de las palabras clave complementarias
                        if any(kw in lower_url for kw in keywords[1:]):
                            candidate_urls.append(url)
                    else:
                        candidate_urls.append(url)
        finally:
            conn.close()

        # Priorizar informes oficiales sobre actas o presentaciones
        candidate_urls.sort(
            key=lambda u: 0 if "informe" in u.lower() else (1 if "resumen" in u.lower() else 2)
        )
        candidate_urls = candidate_urls[:2]

        # Probar candidatos encontrados en la base de datos: solo admitir si NO está ya en inventario (O-1)
        for cand_url in candidate_urls:
            if self.is_url_in_inventory(portal, cand_url):
                continue
            res = self.fetch_and_verify(cand_url)
            if res:
                size, sha256 = res
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

        return None

    def _try_rung_2_series_template(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 2: Plantilla de la serie extrapolada con el período faltante (D-17 + HEAD).
        """
        templates = self.SERIES_TEMPLATES.get((portal, dataset_id), [])
        if not templates:
            return None

        year = int(period[:4])
        yy = f"{year % 100:02d}"
        candidate_urls = []

        if periodicity == "semestral":
            sem = period[-1] if "S" in period else "1"
            # S1 -> junio, S2 -> diciembre
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

        # Validar candidatos con HEAD primero, luego descargar y verificar bytes y hash
        for url in candidate_urls:
            if self._check_head(url):
                res = self.fetch_and_verify(url)
                if res:
                    size, sha256 = res
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

    def _try_rung_3_same_domain_alternate(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 3: Otra ruta dentro del mismo dominio (variaciones sintácticas).
        NOTA: Implementación heurística acotada a variaciones de ruta para bcb/deuda_externa.
        No incluye aún rastreo de sitemap ni buscador interno del portal (desviación declarada).
        """
        # Variaciones de formato y encoding
        year = int(period[:4])
        yy = f"{year % 100:02d}"
        candidate_urls: List[str] = []

        if portal == "bcb" and dataset_id == "deuda_externa":
            sem = period[-1] if "S" in period else "1"
            mon = "jun" if sem == "1" else "dic"
            # Variaciones de espacios no codificados vs codificados y separadores
            variants = [
                f"https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX {mon}{yy}.pdf",
                f"https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX_{mon}{yy}.pdf",
                f"https://www.bcb.gob.bo/webdocs/informes_deudaexterna/depex_{mon}{yy}.pdf",
                f"https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX_{mon}_{year}.pdf",
            ]
            candidate_urls.extend(variants)

        for url in candidate_urls:
            if self._check_head(url):
                res = self.fetch_and_verify(url)
                if res:
                    size, sha256 = res
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

    def _try_rung_4_wayback_archive(
        self, portal: str, dataset_id: str, period: str, periodicity: str
    ) -> Optional[RecoveredPeriod]:
        """
        Escalón 4: Archivo histórico de la web (Wayback Machine).
        NOTA: Consulta la Availability API de Wayback para URLs candidatas predecibles.
        No utiliza la infraestructura completa de wayback_engine (CDX / caché) en esta fase.
        """
        # Formular URLs candidatas a consultar en Wayback Availability API
        candidate_urls = []
        year = int(period[:4])
        yy = f"{year % 100:02d}"

        if portal == "bcb" and dataset_id == "deuda_externa":
            mon = "jun" if period.endswith("S1") else "dic"
            candidate_urls.append(f"https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20{mon}{yy}.pdf")
        elif portal == "ine" and dataset_id == "rendicion_cuentas":
            # Si existía en el inventario pero el portal estuviera caído
            candidate_urls.append(f"https://www.ine.gob.bo/index.php/descarga/rendicion-publica-de-cuentas-{year}")

        for target_url in candidate_urls:
            api = f"https://archive.org/wayback/available?url={quote(target_url, safe=':/?=')}"
            try:
                resp = self._session.get(api, timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json()
                    snapshots = data.get("archived_snapshots", {})
                    closest = snapshots.get("closest", {})
                    if closest.get("available") and closest.get("status") in ("200", 200):
                        snap_url = closest.get("url")
                        res = self.fetch_and_verify(snap_url)
                        if res:
                            size, sha256 = res
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
                                    "original_url": target_url,
                                },
                            )
            except Exception as e:
                logger.debug("Error consultando Wayback para %s: %s", target_url, e)

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
                        return [d.strip().lower() for d in domains if d and isinstance(d, str)]
            except Exception as e:
                logger.debug("Error leyendo allowed_domains de %s: %s", cfg_path, e)

        fallbacks = {
            "bcb": ["bcb.gob.bo", "www.bcb.gob.bo", "deudaexternapublica.bcb.gob.bo"],
            "asfi": ["asfi.gob.bo", "www.asfi.gob.bo"],
            "ine": ["ine.gob.bo", "www.ine.gob.bo"],
        }
        return fallbacks.get(portal.lower(), [f"{portal}.gob.bo"])

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
        regexes = portal_regexes.get(portal.lower(), [rf"\b{re.escape(portal.lower())}\b"])
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

        year_pattern = rf"\b{target_year}\b"
        in_url_year = bool(re.search(year_pattern, url_lower))
        in_content_year = bool(re.search(year_pattern, sample_text))

        if not (in_url_year or in_content_year):
            return False

        if "-S" in p_clean:
            sem_num = p_clean.split("-S")[-1]
            if sem_num == "1":
                sem_terms = [r"\bs1\b", r"\b1sem\b", r"\bsem1\b", r"\bjun\b", r"\bjunio\b", r"\bprimer semestre\b", r"\bi semestre\b"]
            else:
                sem_terms = [r"\bs2\b", r"\b2sem\b", r"\bsem2\b", r"\bdic\b", r"\bdiciembre\b", r"\bsegundo semestre\b", r"\bii semestre\b"]
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

            if not any(domain == ad or domain.endswith("." + ad) for ad in allowed_domains):
                logger.info(
                    "Candidato del agente derivado a cola de herencia B-55 por dominio no autorizado (%s no en %s): %s",
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
                    "reason": "Dominio externo sugerido por LLM (cola de herencia B-55)",
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
