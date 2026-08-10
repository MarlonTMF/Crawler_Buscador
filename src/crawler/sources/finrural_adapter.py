"""
Adaptador específico para la fuente FINRURAL (finrural.org.bo).
Encapsula reglas de clasificación de datasets, listas de exclusión y patrones temporales de FINRURAL.
"""

import re
from pathlib import Path
from typing import Optional, Dict, Any
from crawler.sources.base_adapter import BaseSourceAdapter


class FinruralAdapter(BaseSourceAdapter):
    """Adaptador de fuente para FINRURAL."""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parents[3] / "config" / "source_finrural.yaml"
        super().__init__(config_path)

        self.excluded_keywords = self.config.get("classification", {}).get("excluded_path_keywords", [])
        self.filename_pattern = re.compile(
            self.config.get("period_extraction", {}).get(
                "filename_pattern",
                r"financiera_(?P<month>0[1-9]|1[0-2])_(?P<year>20\d{2})\.pdf"
            ),
            re.IGNORECASE
        )
        self.months_map = self.config.get("period_extraction", {}).get("months_es", {})

    def is_url_excluded(self, url: str) -> bool:
        """Comprueba si la URL contiene palabras clave de rutas excluidas (historia, misión, glosario, etc.)."""
        url_lower = url.lower()
        for kw in self.excluded_keywords:
            if kw.lower() in url_lower:
                return True
        return False

    def classify_dataset(self, url: str, anchor_text: str = "") -> Optional[str]:
        """Clasifica la URL en 'reporte_financiero_mensual' o 'archivo_historico'."""
        url_lower = url.lower()
        anchor_lower = anchor_text.lower()

        if "archivo-historico" in url_lower or "histórico" in anchor_lower or "historico" in anchor_lower:
            return "archivo_historico"

        if (
            "reporte-financiero-mensual" in url_lower
            or "/archivos/info_financiera/" in url_lower
            or "financiera_" in url_lower
            or "reporte financiero" in anchor_lower
            or "boletín financiero" in anchor_lower
        ):
            return "reporte_financiero_mensual"

        return "reporte_financiero_mensual"

    def match_filename_pattern(self, text: str) -> Optional[Dict[str, str]]:
        """Extrae mes y año si el texto o URL coincide con el patrón `financiera_MM_YYYY.pdf`."""
        match = self.filename_pattern.search(text)
        if match:
            return match.groupdict()
        return None
