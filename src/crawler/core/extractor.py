"""
Extractor de metadatos y vigencia temporal en 4 capas (RF-08 y ADR-003).
Aplica un orden de costo creciente: URL pattern -> DOM context -> HTTP Metadata -> Content parsing.
"""

import re
import hashlib
import calendar
from urllib.parse import urlparse, unquote
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
            "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
            "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12
        }

    def _format_period(self, year: int, month: int) -> Tuple[str, str]:
        """Calcula el primer y último día del mes en formato ISO YYYY-MM-DD."""
        _, last_day = calendar.monthrange(year, month)
        period_start = f"{year:04d}-{month:02d}-01"
        period_end = f"{year:04d}-{month:02d}-{last_day:02d}"
        return period_start, period_end

    def extract_date_layer1_url(self, url: str) -> Optional[DateExtractionResult]:
        """
        Capa 1: Extrae la fecha buscando patrones en carpetas (published_at) y
        en el nombre del archivo (period_start / period_end).

        Patrones reales de carpetas:
        - /AAAA-MM/ (ASFI)
        - /AAAA/MM/ o /AAAA/MM/DD/ (BCB)

        Patrones de archivo:
        - _MM_AAAA, _AAAA_MM
        - AAAAMM_
        - DDmesAAAA o AAAA-DDmes (ej. 9 DE SEPTIEMBRE 2026, 28septiembre2017)
        - mes AAAA (ej. Septiembre 2025, jun26)
        - DD_MM_AAAA (ej. 27_07_2026)
        - Rango AAAA-AAAA
        - Año suelto (ej. MEMORIA_2025.pdf)
        """
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

        parsed = urlparse(url)
        raw_path = unquote(parsed.path)
        parts = [p for p in raw_path.split("/") if p]
        folder = "/".join(parts[:-1]) if len(parts) > 1 else ""
        filename = parts[-1] if parts else ""
        if parsed.fragment:
            f_parts = [p for p in unquote(parsed.fragment).split("/") if p]
            if f_parts:
                filename = f_parts[-1]

        published_at = None
        folder_str = "/" + folder + "/"

        # 1. Extracción de carpeta (published_at)
        # /YYYY/MM/DD/
        m_ymd = re.search(r"/(?P<y>20\d{2})/(?P<m>0[1-9]|1[0-2])/(?P<d>0[1-9]|[12]\d|3[01])/", folder_str)
        if m_ymd:
            published_at = f"{m_ymd.group('y')}-{m_ymd.group('m')}-{m_ymd.group('d')}"
        else:
            # /YYYY/MM/
            m_ym = re.search(r"/(?P<y>20\d{2})/(?P<m>0[1-9]|1[0-2])/", folder_str)
            if m_ym:
                published_at = f"{m_ym.group('y')}-{m_ym.group('m')}-01"
            else:
                # /YYYY-MM/
                m_dash = re.search(r"/(?P<y>20\d{2})-(?P<m>0[1-9]|1[0-2])/", folder_str)
                if m_dash:
                    published_at = f"{m_dash.group('y')}-{m_dash.group('m')}-01"
                else:
                    # Carpeta con año (ej. INE: /informes-auditoria-interna-2021/)
                    # Se exige que el segmento contenga texto (letras) para evitar IDs numéricos de CMS (O-6)
                    for seg in parts[:-1]:
                        if re.search(r"[a-zA-Z]", seg):
                            m_fy = re.search(r"(?<!\d)(?P<y>20\d{2}|19\d{2})(?!\d)", seg)
                            if m_fy:
                                published_at = f"{m_fy.group('y')}-01-01"
                                break

        # 2. Extracción de período en nombre de archivo (period_start / period_end)
        period_start = None
        period_end = None
        fname_lower = filename.lower()

        # a) DD_MM_AAAA
        m_dmy = re.search(r"(?<!\d)(?P<d>0[1-9]|[12]\d|3[01])_(?P<m>0[1-9]|1[0-2])_(?P<y>20\d{2})(?!\d)", filename)
        if m_dmy:
            y, m, d = m_dmy.group("y"), m_dmy.group("m"), m_dmy.group("d")
            period_start = f"{y}-{m}-{d}"
            period_end = f"{y}-{m}-{d}"

        # b) DDmesAAAA o "DD de mes de AAAA" (O-1)
        if not period_start:
            m_exp = re.search(
                r"(?<!\d)(?P<d>0?[1-9]|[12]\d|3[01])\s+de\s+(?P<mes>[a-záéíóú]+)\s+de\s+(?P<y>20\d{2}|19\d{2})(?!\d)",
                fname_lower,
            )
            if m_exp:
                mes_str = m_exp.group("mes")
                if mes_str in self.months_es:
                    m_num = self.months_es[mes_str]
                    y_val = int(m_exp.group("y"))
                    d_val = int(m_exp.group("d"))
                    period_start = f"{y_val:04d}-{m_num:02d}-{d_val:02d}"
                    period_end = f"{y_val:04d}-{m_num:02d}-{d_val:02d}"

        if not period_start:
            for m_ddmes in re.finditer(
                r"(?:(?P<y1>20\d{2})[-_\s]+)?(?P<d>0?[1-9]|[12]\d|3[01])\s*(?:de|-|_|\s)\s*(?P<mes>[a-záéíóú]+)(?:\s*(?:de|-|_|\s)\s*(?P<y2>20\d{2}))?",
                fname_lower,
            ):
                if m_ddmes.group("y1") or m_ddmes.group("y2"):
                    mes_str = m_ddmes.group("mes")
                    if mes_str in self.months_es:
                        m_num = self.months_es[mes_str]
                        y_val = int(m_ddmes.group("y1") or m_ddmes.group("y2"))
                        d_val = int(m_ddmes.group("d"))
                        period_start = f"{y_val:04d}-{m_num:02d}-{d_val:02d}"
                        period_end = f"{y_val:04d}-{m_num:02d}-{d_val:02d}"
                        break

        # c) _MM_AAAA, MM-AAAA, MM_AAAA con espacio/separador (O-1)
        if not period_start:
            m_my = re.search(r"(?:^|[\s_\-\(\[])(?P<m>0[1-9]|1[0-2])[_\-](?P<y>20\d{2})(?!\d)", filename)
            if m_my:
                y, m = int(m_my.group("y")), int(m_my.group("m"))
                period_start, period_end = self._format_period(y, m)
            else:
                m_ym_rev = re.search(r"(?:^|[\s_\-\(\[])(?P<y>20\d{2})[_\-](?P<m>0[1-9]|1[0-2])(?!\d)", filename)
                if m_ym_rev:
                    y, m = int(m_ym_rev.group("y")), int(m_ym_rev.group("m"))
                    period_start, period_end = self._format_period(y, m)

        # d) AAAAMM_
        if not period_start:
            m_ym_ = re.search(r"(?<!\d)(?P<y>20\d{2})(?P<m>0[1-9]|1[0-2])_", filename)
            if m_ym_:
                y, m = int(m_ym_.group("y")), int(m_ym_.group("m"))
                period_start, period_end = self._format_period(y, m)

        # e) mes AAAA (ej. Septiembre 2025, jun26, Marzo__2026, etc. O-1)
        if not period_start:
            for mes_str, m_num in sorted(self.months_es.items(), key=lambda x: -len(x[0])):
                pattern = rf"\b{mes_str}[\s_\-]*(?P<y>20\d{{2}}|(?<!\d)2\d(?!\d))"
                m_mes = re.search(pattern, fname_lower)
                if m_mes:
                    raw_y = m_mes.group("y")
                    y = int(raw_y) if len(raw_y) == 4 else 2000 + int(raw_y)
                    period_start, period_end = self._format_period(y, m_num)
                    break

        # f) Rango AAAA-AAAA o pegado AAAAYYYY (ej. PEI-2021-2025, 19902014)
        if not period_start:
            m_yrange = re.search(r"(?<!\d)(?P<y1>20\d{2})-(?P<y2>20\d{2})(?!\d)", filename)
            if m_yrange:
                period_start = f"{m_yrange.group('y1')}-01-01"
                period_end = f"{m_yrange.group('y2')}-12-31"
            else:
                m_y8 = re.search(r"(?<!\d)(?P<y1>19\d{2})(?P<y2>20\d{2})(?!\d)", filename)
                if m_y8:
                    period_start = f"{m_y8.group('y1')}-01-01"
                    period_end = f"{m_y8.group('y2')}-12-31"

        # g) Año suelto (fallback de año, O-2)
        is_year_fallback = False
        if not period_start:
            m_y = re.search(r"(?<!\d)(?P<y>19\d{2}|20\d{2})(?!\d)", filename)
            if m_y:
                y = int(m_y.group("y"))
                period_start = f"{y:04d}-01-01"
                period_end = f"{y:04d}-12-31"
                is_year_fallback = True

        # Si no hubo coincidencia en carpeta ni archivo
        if not published_at and not period_start:
            return None

        # Asignación de confianza y método según regla B-50 / O-2
        if published_at and period_start:
            confidence = "high"
            method = "url_year_fallback" if is_year_fallback else "url_pattern"
        elif published_at and not period_start:
            confidence = "low"
            method = "url_folder"
        else:
            confidence = "medium"
            method = "url_year_fallback" if is_year_fallback else "url_pattern"

        return DateExtractionResult(
            period_start=period_start,
            period_end=period_end,
            published_at=published_at,
            method=method,
            confidence=confidence
        )

    def extract_date_layer2_dom(self, anchor_text: str, context_text: str) -> Optional[DateExtractionResult]:
        """Capa 2: Busca nombres de meses en español y años en el texto ancla o contexto HTML."""
        combined_text = f"{anchor_text} {context_text}".lower()

        for month_name, month_num in sorted(self.months_es.items(), key=lambda x: -len(x[0])):
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
        Combina la fecha de publicación y el período detectado entre capas.
        """
        # Intentar Capa 1 (URL Pattern)
        res_l1 = self.extract_date_layer1_url(url)
        if res_l1:
            # Si solo se detectó la carpeta de publicación pero falta el período, buscar en Capa 2
            if res_l1.published_at and not res_l1.period_start:
                res_l2 = self.extract_date_layer2_dom(anchor_text, context_text)
                if res_l2 and res_l2.period_start:
                    _, http_meta = self.extract_date_layer3_http(url)
                    return DateExtractionResult(
                        period_start=res_l2.period_start,
                        period_end=res_l2.period_end,
                        published_at=res_l1.published_at,
                        method="url_and_dom",
                        confidence="high"
                    ), http_meta

            _, http_meta = self.extract_date_layer3_http(url)
            return res_l1, http_meta

        # Intentar Capa 2 (DOM Context)
        res_l2 = self.extract_date_layer2_dom(anchor_text, context_text)
        if res_l2:
            _, http_meta = self.extract_date_layer3_http(url)
            if http_meta.get("last_modified"):
                res_l2.published_at = http_meta["last_modified"]
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
