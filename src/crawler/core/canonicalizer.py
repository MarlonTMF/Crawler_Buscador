"""
Canonicalizador y deduplicador de recursos (ADR-005).
Normaliza URLs eliminando parámetros de cache-busting (?x16877) y rastreo, y genera resource_keys estables.
"""

from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import List, Set, Dict, Any, Optional
from crawler.sources.base_adapter import BaseSourceAdapter


class Canonicalizer:
    """Procesa URLs para generar formas canónicas e identidades de recurso estables."""

    def __init__(self, adapter: BaseSourceAdapter):
        self.adapter = adapter
        self.drop_params = set(adapter.drop_query_params)

    def canonicalize_url(self, url: str) -> str:
        """
        Remueve parámetros no semánticos (utm_*, x16877, fbclid) y fragmentos (#) de la URL.
        
        Returns:
            str: URL canónica normalizada.
        """
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)

        # Filtrar parámetros a ignorar
        clean_query = {}
        for k, v in query_dict.items():
            if k.lower() not in self.drop_params and not k.lower().startswith("utm_"):
                clean_query[k] = v

        new_query = urlencode(clean_query, doseq=True) if clean_query else ""
        clean_parsed = parsed._replace(query=new_query, fragment="")
        return urlunparse(clean_parsed)

    def generate_resource_key(self, source_id: str, dataset_id: str, period_end: Optional[str], file_type: str, canonical_url: str) -> str:
        """
        Genera una clave de identidad estable (ADR-005) para el recurso.
        Ejemplo: 'finrural:reporte_financiero_mensual:2026-01-31:pdf'
        
        Si no hay período disponible, usa la ruta normalizada del archivo.
        """
        if period_end:
            period_token = period_end[:7]  # YYYY-MM
            return f"{source_id}:{dataset_id}:{period_token}:{file_type.lower()}"

        # Fallback sin período: usa el nombre base de la ruta
        path_segments = [p for p in urlparse(canonical_url).path.split("/") if p]
        filename = path_segments[-1] if path_segments else "document"
        name_no_ext = filename.rsplit(".", 1)[0]
        return f"{source_id}:{dataset_id}:{name_no_ext}:{file_type.lower()}"
