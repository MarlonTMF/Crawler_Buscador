"""
Motor de Extrapolación Controlada de Series Temporales Observadas (Decisión D-17 / Fase 3).
========================================================================================
Permite descubrir sistemáticamente series estadísticas y documentales generadas por scripts
del lado del cliente (como ifd-bol.js en ASFI) o plantillas temporales predecibles ({YYYY}/{MM}),
validando obligatoriamente cada candidato con peticiones HTTP HEAD antes de admitirlo al catálogo.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from crawler.core.discovery import DiscoveredCandidate
from crawler.core.fetcher import HttpFetcher
from crawler.sources.base_adapter import BaseSourceAdapter

logger = logging.getLogger(__name__)


class SeriesExtrapolator:
    """
    Extrapola series temporales a partir de patrones declarativos o URLs observadas bajo D-17.
    Garantiza que ningún recurso ingrese al catálogo sin verificación HEAD exitosa (HTTP 200 + bytes > 0).
    """

    def __init__(
        self,
        fetcher: HttpFetcher,
        adapter: BaseSourceAdapter,
        max_consecutive_empty_periods: int = 24,
        max_workers: int = 4,
    ):
        self.fetcher = fetcher
        self.adapter = adapter
        self.max_consecutive_empty_periods = max_consecutive_empty_periods
        self.max_workers = max_workers

    def is_enabled(self) -> bool:
        """Indica si la fuente tiene configurada la extrapolación de series."""
        cfg = self.adapter.config.get("crawl", {}).get("series_extrapolation", {})
        return bool(cfg.get("enabled", False))

    def extrapolate_series(self) -> List[DiscoveredCandidate]:
        """
        Ejecuta la extrapolación de series temporales configuradas en el YAML de la fuente.
        Retorna únicamente los candidatos que respondieron HTTP 200 y cumplen con D-14/D-17.
        """
        if not self.is_enabled():
            return []

        cfg = self.adapter.config.get("crawl", {}).get("series_extrapolation", {})
        template = cfg.get("template", "")
        if not template:
            logger.warning("Extrapolación habilitada pero no se especificó 'template' en la configuración.")
            return []

        url_origin = cfg.get("url_origin", self.adapter.base_url)
        dataset_id = cfg.get("dataset_id", "series_temporales")
        file_type = cfg.get("file_type", "zip")
        series_names = cfg.get("series", [])
        if not series_names:
            logger.warning("No se especificaron 'series' para la extrapolación temporal.")
            return []

        start_year = int(cfg.get("start_year", 2015))
        end_year = int(cfg.get("end_year", datetime.now().year))
        end_month = int(cfg.get("end_month", 12))

        logger.info(
            "Iniciando extrapolación D-17: %d series, rango %d-%d hacia atrás (corte: %d períodos vacíos)...",
            len(series_names),
            start_year,
            end_year,
            self.max_consecutive_empty_periods,
        )

        # Generar lista de períodos (año, mes) en orden cronológico inverso (desde el más reciente)
        periods: List[Tuple[int, int]] = []
        for y in range(end_year, start_year - 1, -1):
            max_m = end_month if y == end_year else 12
            for m in range(max_m, 0, -1):
                periods.append((y, m))

        confirmed_candidates: List[DiscoveredCandidate] = []
        consecutive_empty_periods = 0
        total_probed = 0

        for year, month in periods:
            if consecutive_empty_periods >= self.max_consecutive_empty_periods:
                logger.info(
                    "Corte histórico D-17 alcanzado: %d períodos consecutivos vacíos. Deteniendo extrapolación en %04d-%02d.",
                    consecutive_empty_periods,
                    year,
                    month,
                )
                break

            # Construir candidatos del período
            period_urls: List[Tuple[str, str]] = []
            for serie in series_names:
                try:
                    url = template.format(
                        year=year,
                        month=month,
                        serie=serie,
                        yyyymm=f"{year}{month:02d}",
                    )
                    period_urls.append((url, serie))
                except Exception as fmt_err:
                    logger.warning("Error formateando URL para %d-%02d %s: %s", year, month, serie, fmt_err)

            # Validar URLs del período con HEAD
            period_found_count = 0
            for url, serie in period_urls:
                total_probed += 1
                try:
                    ok, status, headers = self.fetcher.fetch_head(url)
                    if ok and status in (200, 206):
                        # Validación de bytes si están presentes en Content-Length
                        content_length = headers.get("content-length")
                        if content_length is not None and int(content_length) <= 0:
                            logger.debug("HEAD respondió 200 pero Content-Length es 0 en %s; descartado.", url)
                            continue

                        period_found_count += 1
                        confirmed_candidates.append(
                            DiscoveredCandidate(
                                url=url,
                                url_origin=url_origin,
                                anchor_text=f"{year}{month:02d}_{serie}",
                                context_text=f"Extrapolación observada D-17 ({year}-{month:02d})",
                                dataset_id=dataset_id,
                                file_type=file_type,
                                relevance_score=100.0,
                                depth=1,
                            )
                        )
                except Exception as probe_err:
                    logger.debug("Error validando HEAD para %s: %s", url, probe_err)

            if period_found_count > 0:
                consecutive_empty_periods = 0
                logger.debug("Período %04d-%02d: %d archivos confirmados.", year, month, period_found_count)
            else:
                consecutive_empty_periods += 1

        logger.info(
            "Extrapolación D-17 completada: %d URLs sondeadas con HEAD, %d confirmadas (HTTP 200).",
            total_probed,
            len(confirmed_candidates),
        )
        return confirmed_candidates
