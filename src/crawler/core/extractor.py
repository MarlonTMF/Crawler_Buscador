"""
Extractor de metadatos y vigencia temporal en 4 capas (RF-08 y ADR-003).
Aplica un orden de costo creciente: URL pattern -> DOM context -> HTTP Metadata -> Content parsing.
"""

import re
import hashlib
import calendar
from urllib.parse import urlparse
from typing import Optional, Dict, Any, Tuple, List
from crawler.core.fetcher import HttpFetcher
from crawler.sources.base_adapter import BaseSourceAdapter


class DateExtractionResult:
    """Resultado derivado del análisis de fechas de un recurso."""

    def __init__(
        self,
        period_start: Optional[str],
        period_end: Optional[str],
        published_at: Optional[str],
        method: str,
        confidence: str
    ):
        self.period_start = period_start
        self.period_end = period_end
        self.published_at = published_at
        self.method = method
        self.confidence = confidence


class MetadataExtractor:
    """Extractor de metadatos de vigencia temporal, tamaño y hash de contenido."""

    def __init__(self, fetcher: HttpFetcher, adapter: BaseSourceAdapter):
        self.fetcher = fetcher
        self.adapter = adapter
        self.months_es = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
        }

    def _format_period(self, year: int, month: int) -> Tuple[str, str]:
        """Calcula el primer y último día del mes en formato ISO YYYY-MM-DD."""
        _, last_day = calendar.monthrange(year, month)
        period_start = f"{year:04d}-{month:02d}-01"
        period_end = f"{year:04d}-{month:02d}-{last_day:02d}"
        return period_start, period_end

    def extract_date_layer1_url(self, url: str) -> Optional[DateExtractionResult]:
        """Capa 1: Extrae la fecha buscando patrones como `financiera_MM_YYYY.pdf` en la URL."""
        # Intenta coincidencia mediante la regla del adaptador si aplica
        if hasattr(self.adapter, "match_filename_pattern"):
            matched = self.adapter.match_filename_pattern(url)
            if matched:
                month = int(matched["month"])
                year = int(matched["year"])
                start, end = self._format_period(year, month)
                return DateExtractionResult(
                    period_start=start,
                    period_end=end,
                    published_at=None,
                    method="url_pattern",
                    confidence="high"
                )

        # Regex genérico de respaldo: _MM_YYYY o _YYYY_MM
        gen_match = re.search(r"_(?P<m>0[1-9]|1[0-2])_(?P<y>20\d{2})\b", url)
        if gen_match:
            month = int(gen_match.group("m"))
            year = int(gen_match.group("y"))
            start, end = self._format_period(year, month)
            return DateExtractionResult(start, end, None, "url_pattern", "high")

        return None

    def extract_date_layer2_dom(self, anchor_text: str, context_text: str) -> Optional[DateExtractionResult]:
        """Capa 2: Busca nombres de meses en español y años en el texto ancla o contexto HTML."""
        combined_text = f"{anchor_text} {context_text}".lower()

        for month_name, month_num in self.months_es.items():
            if month_name in combined_text:
                year_match = re.search(r"\b(20\d{2})\b", combined_text)
                if year_match:
                    year = int(year_match.group(1))
                    start, end = self._format_period(year, month_num)
                    return DateExtractionResult(
                        period_start=start,
                        period_end=end,
                        published_at=None,
                        method="dom_context",
                        confidence="medium"
                    )

        return None

    def extract_date_layer3_http(self, url: str) -> Tuple[Optional[DateExtractionResult], Dict[str, Any]]:
        """Capa 3: Consulta headers HTTP (HEAD) para obtener Last-Modified, Content-Length, ETag."""
        http_meta: Dict[str, Any] = {
            "content_length_bytes": None,
            "etag": None,
            "last_modified": None
        }
        parsed = urlparse(url)
        if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
            return None, http_meta

        success, status, headers = self.fetcher.fetch_head(url)
        if not success or not headers:
            return None, http_meta

        if "content-length" in headers:
            try:
                http_meta["content_length_bytes"] = int(headers["content-length"])
            except ValueError:
                pass

        http_meta["etag"] = headers.get("etag")
        http_meta["last_modified"] = headers.get("last-modified")

        if http_meta["last_modified"]:
            return DateExtractionResult(
                period_start=None,
                period_end=None,
                published_at=http_meta["last_modified"],
                method="http_header",
                confidence="low"
            ), http_meta

        return None, http_meta

    def resolve_date_and_metadata(
        self,
        url: str,
        anchor_text: str,
        context_text: str,
        download_bytes: bool = False
    ) -> Tuple[DateExtractionResult, Dict[str, Any]]:
        """
        Ejecuta la jerarquía completa de extracción de fecha y metadatos.
        
        Returns:
            Tuple[DateExtractionResult, Dict[str, Any]]
        """
        # Intentar Capa 1 (URL Pattern)
        res_l1 = self.extract_date_layer1_url(url)
        if res_l1:
            _, http_meta = self.extract_date_layer3_http(url)
            return res_l1, http_meta

        # Intentar Capa 2 (DOM Context)
        res_l2 = self.extract_date_layer2_dom(anchor_text, context_text)
        if res_l2:
            _, http_meta = self.extract_date_layer3_http(url)
            return res_l2, http_meta

        # Intentar Capa 3 (HTTP Header)
        res_l3, http_meta = self.extract_date_layer3_http(url)
        if res_l3:
            return res_l3, http_meta

        # Fallback predeterminado
        fallback_res = DateExtractionResult(
            period_start=None,
            period_end=None,
            published_at=None,
            method="unknown",
            confidence="unknown"
        )
        return fallback_res, http_meta

    @staticmethod
    def compute_sha256(content_bytes: bytes) -> str:
        """Calcula el hash SHA-256 de los bytes de un archivo."""
        return hashlib.sha256(content_bytes).hexdigest()
