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
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, unquote

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
    ):
        self.fetcher = fetcher or HttpFetcher()
        self.base_output_dir = base_output_dir
        self.base_config_dir = base_config_dir
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": getattr(self.fetcher, "user_agent", "DataX-Prospector/1.0 (+http://datax.org)")
        })

    def verify_content_bytes(self, content: bytes) -> Tuple[int, str]:
        """Calcula el tamaño en bytes y el hash SHA-256 del contenido."""
        if not content:
            return 0, ""
        size = len(content)
        sha256 = hashlib.sha256(content).hexdigest()
        return size, sha256

    def fetch_and_verify(self, url: str) -> Optional[Tuple[int, str]]:
        """Realiza descarga directa verificando bytes > 0 y hash SHA-256."""
        try:
            r = self._session.get(url, timeout=self.timeout, verify=False, stream=True)
            if r.status_code not in (200, 206):
                return None
            hasher = hashlib.sha256()
            total_size = 0
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    hasher.update(chunk)
                    total_size += len(chunk)
            if total_size <= 0:
                return None
            return total_size, hasher.hexdigest()
        except Exception as e:
            logger.debug("Error descargando %s: %s", url, e)
            return None

    def _check_head(self, url: str) -> bool:
        """Verifica existencia de recurso con petición HTTP HEAD (status 200, length > 0)."""
        try:
            r = self._session.head(url, timeout=self.timeout, verify=False, allow_redirects=True)
            if r.status_code in (200, 206):
                cl = r.headers.get("content-length")
                if cl is not None and int(cl) <= 0:
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

    def recover_period(
        self, portal: str, dataset_id: str, period: str, periodicity: str = "anual"
    ) -> Optional[RecoveredPeriod]:
        """
        Busca un período faltante a través de los cuatro escalones en orden estricto de menor a mayor riesgo.
        Se detiene en el primer escalón que tenga éxito.
        Verifica en todos los escalones que la URL recuperada no exista previamente en el inventario (O-1).
        """
        for rung_fn in (
            self._try_rung_1_known_url,
            self._try_rung_2_series_template,
            self._try_rung_3_same_domain_alternate,
            self._try_rung_4_wayback_archive,
        ):
            res = rung_fn(portal, dataset_id, period, periodicity)
            if res:
                if self.is_url_in_inventory(portal, res.url):
                    logger.debug("Candidato %s descartado: ya existe en inventory.db", res.url)
                    continue
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

        return all_recovered
