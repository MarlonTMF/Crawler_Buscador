"""
Adaptador específico para la Bolsa Boliviana de Valores (bbv.com.bo).
Encapsula reglas de clasificación de datasets y rutas excluidas para la BBV.
"""

import re
from pathlib import Path
from typing import Optional, Dict, Any
from crawler.sources.base_adapter import BaseSourceAdapter


class BbvAdapter(BaseSourceAdapter):
    """Adaptador de fuente para la Bolsa Boliviana de Valores (BBV)."""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parents[3] / "config" / "source_bbv.yaml"
        super().__init__(config_path)

        self.excluded_keywords = self.config.get("classification", {}).get("excluded_path_keywords", [])

    def is_url_excluded(self, url: str) -> bool:
        """Comprueba si la URL contiene palabras clave de rutas excluidas (historia, contacto, etc.)."""
        url_lower = url.lower()
        for kw in self.excluded_keywords:
            if kw.lower() in url_lower:
                return True
        return False

    def classify_dataset(self, url: str, anchor_text: str = "") -> Optional[str]:
        """Clasifica la URL en datasets de la Bolsa Boliviana de Valores."""
        url_lower = url.lower()
        anchor_lower = anchor_text.lower()

        if "memorias-anuales" in url_lower or "memoria" in anchor_lower:
            return "memorias_anuales"

        if "informacion-financiera" in url_lower or "financiera" in anchor_lower:
            return "informacion_financiera_bbv"

        if "hechos-relevantes" in url_lower or "hechos relevantes" in anchor_lower:
            return "hechos_relevantes"

        if "estadisticas" in url_lower or "mercados" in url_lower or "resumen" in anchor_lower:
            return "estadisticas_bursatiles"

        return "estadisticas_bursatiles"
